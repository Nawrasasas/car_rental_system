# PATH: apps/invoices/models.py
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.customers.models import Customer
from apps.accounting.models import Account, JournalEntry


# =========================================================
# أنواع رسوم الفاتورة السريعة
# =========================================================
class FeeType(models.TextChoices):
    DAMAGE_FEE  = 'damage_fee',  'Damage Fee'
    TRAFFIC_FEE = 'traffic_fee', 'Traffic Fee'
    LATE_FEE    = 'late_fee',    'Late Fee'
    OTHER       = 'other',       'Other'


class Invoice(models.Model):
    STATUS_CHOICES = (
        ("draft",    "Draft"),
        ("posted",   "Posted"),
        ("reversed", "Reversed"),
    )

    invoice_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        verbose_name="Invoice Number",
    )

    invoice_date = models.DateField(
        default=timezone.now,
        verbose_name="Invoice Date",
    )

    due_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Due Date",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
        verbose_name="Status",
    )

    from_company = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="From Company",
    )

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Customer",
    )

    receivable_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoice_receivable_entries",
        verbose_name="Receivable Account",
    )

    revenue_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoice_revenue_entries",
        verbose_name="Revenue Account",
    )

    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="posted_invoices",
        verbose_name="Journal Entry",
        editable=False,
    )

    reversed_journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reversed_invoices",
        verbose_name="Reversed Journal Entry",
        editable=False,
    )

    # ← blank=True لأن Quick Fee لا يشترط اسم عميل يدوي
    customer_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Customer Name",
    )

    customer_email = models.EmailField(
        blank=True,
        verbose_name="Customer Email",
    )

    customer_phone = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Customer Phone",
    )

    customer_address = models.TextField(
        blank=True,
        verbose_name="Customer Address",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="Notes",
    )

    # =========================================================
    # حقول الفاتورة السريعة
    # =========================================================
    is_quick_fee = models.BooleanField(
        default=False,
        verbose_name="Quick Fee Invoice",
        help_text=(
            "Enable for simple fee invoices (Damage / Traffic / Late fee). "
            "Customer fields are not required."
        ),
    )

    fee_type = models.CharField(
        max_length=20,
        choices=FeeType.choices,
        blank=True,
        verbose_name="Fee Type",
    )

    fee_type_other = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Other (specify)",
    )

    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Subtotal",
    )

    total_tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Total Tax",
    )

    grand_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Grand Total",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"

    def __str__(self):
        label = self.customer_name or self.get_fee_type_display() or "—"
        return f"{self.invoice_number or 'INV'} - {label}"

    def is_draft(self):
        return self.status == "draft"

    def is_posted(self):
        return self.status == "posted"

    def is_reversed(self):
        return self.status == "reversed"

    def can_edit_core_fields(self):
        return self.is_draft()

    # =========================================================
    # clean
    # =========================================================
    def clean(self):
        super().clean()

        if self.receivable_account and not self.receivable_account.is_active:
            raise ValidationError("الحساب المدين المختار غير نشط.")

        if self.revenue_account and not self.revenue_account.is_active:
            raise ValidationError("حساب الإيراد المختار غير نشط.")

        # --- Quick Fee: تعبئة customer_name تلقائياً ---
        if self.is_quick_fee:
            if not self.customer_name:
                if self.fee_type == FeeType.OTHER:
                    self.customer_name = self.fee_type_other or "Quick Fee"
                elif self.fee_type:
                    self.customer_name = dict(FeeType.choices).get(self.fee_type, "Quick Fee")
                else:
                    self.customer_name = "Quick Fee Invoice"

        # --- فاتورة عادية: نسخ بيانات العميل تلقائياً ---
        if not self.is_quick_fee and self.customer:
            if not self.customer_name:
                self.customer_name = self.customer.full_name
            if not self.customer_email:
                self.customer_email = self.customer.email or ""
            if not self.customer_phone:
                self.customer_phone = self.customer.phone or ""
            if not self.customer_address:
                self.customer_address = self.customer.address or ""

        # --- قفل الحقول بعد الترحيل ---
        if self.pk and not self.can_edit_core_fields():
            original = Invoice.objects.filter(pk=self.pk).first()
            if original:
                changed_after_post = (
                    original.receivable_account_id != self.receivable_account_id
                    or original.revenue_account_id  != self.revenue_account_id
                    or original.invoice_date        != self.invoice_date
                    or original.customer_id         != self.customer_id
                    or original.customer_name       != self.customer_name
                    or original.customer_email      != self.customer_email
                    or original.customer_phone      != self.customer_phone
                    or original.customer_address    != self.customer_address
                    or original.from_company        != self.from_company
                    or original.is_quick_fee        != self.is_quick_fee
                    or original.fee_type            != self.fee_type
                )
                if changed_after_post:
                    raise ValidationError("لا يمكن تعديل الحقول الأساسية بعد ترحيل الفاتورة أو عكسها.")

    # =========================================================
    # save
    # =========================================================
    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")

        internal_safe_update_fields = {
            "subtotal", "total_tax", "grand_total", "updated_at",
            "status", "journal_entry", "reversed_journal_entry",
        }

        internal_only_update = update_fields is not None and set(update_fields).issubset(
            internal_safe_update_fields
        )

        if not internal_only_update:
            self.full_clean()

        if not self.invoice_number:
            from apps.accounting.services import (
                SequenceResetPolicy,
                generate_sequential_number,
            )
            self.invoice_number = generate_sequential_number(
                model_class=Invoice,
                field_name="invoice_number",
                prefix="INV",
                doc_date=self.invoice_date,
                reset_policy=SequenceResetPolicy.MONTHLY,
            )

        return super().save(*args, **kwargs)

    # =========================================================
    # validate_for_post
    # =========================================================
    def validate_for_post(self):
        if not self.pk:
            raise ValidationError("يجب حفظ الفاتورة أولًا قبل الترحيل.")

        if not self.is_draft():
            raise ValidationError("يمكن ترحيل الفاتورة فقط إذا كانت حالتها draft.")

        if self.journal_entry_id:
            raise ValidationError("هذه الفاتورة مرتبطة أصلًا بقيد محاسبي.")

        # الحسابات مطلوبة فقط للفواتير العادية —
        # Quick Fee تأخذ حساباتها تلقائياً من الكود في post()
        if not self.is_quick_fee:
            if not self.receivable_account:
                raise ValidationError("يجب تحديد حساب الذمم قبل ترحيل الفاتورة.")
            if not self.revenue_account:
                raise ValidationError("يجب تحديد حساب الإيراد قبل ترحيل الفاتورة.")

        if not self.items.exists():
            raise ValidationError("لا يمكن ترحيل فاتورة بدون بنود.")

        if Decimal(self.grand_total or 0) <= Decimal("0.00"):
            raise ValidationError("إجمالي الفاتورة يجب أن يكون أكبر من صفر.")

    # =========================================================
    # validate_for_reverse
    # =========================================================
    def validate_for_reverse(self):
        if not self.pk:
            raise ValidationError("هذه الفاتورة غير محفوظة بعد.")

        if not self.is_posted():
            raise ValidationError("يمكن عكس الفاتورة فقط إذا كانت حالتها posted.")

        if not self.journal_entry_id:
            raise ValidationError("لا يوجد قيد أصلي مرتبط بهذه الفاتورة لعكسه.")

        if self.reversed_journal_entry_id:
            raise ValidationError("تم إنشاء القيد العكسي لهذه الفاتورة مسبقًا.")

    # =========================================================
    # post
    # =========================================================
    @transaction.atomic
    def post(self):
        self.validate_for_post()

        from apps.accounting.services import create_journal_entry

        # --- Quick Fee: جلب الحسابات من الكود مباشرة ---
        if self.is_quick_fee:
            try:
                self.receivable_account = Account.objects.get(code='1201')
                self.revenue_account    = Account.objects.get(code='4300')
                self.save(update_fields=["receivable_account", "revenue_account", "updated_at"])
            except Account.DoesNotExist as e:
                raise ValidationError(
                    f"حساب مطلوب للفاتورة السريعة غير موجود في شجرة الحسابات: {e}"
                )

        amount = Decimal(self.grand_total or 0).quantize(Decimal("0.01"))

        entry = create_journal_entry(
            entry_date=self.invoice_date,
            description=f"Invoice post {self.invoice_number}",
            source_app="invoices",
            source_model="Invoice",
            source_id=self.id,
            lines=[
                {
                    "account":     self.receivable_account,
                    "debit":       amount,
                    "credit":      Decimal("0.00"),
                    "description": f"Receivable for invoice {self.invoice_number}",
                },
                {
                    "account":     self.revenue_account,
                    "debit":       Decimal("0.00"),
                    "credit":      amount,
                    "description": f"Revenue for invoice {self.invoice_number}",
                },
            ],
        )

        self.journal_entry = entry
        self.status = "posted"
        self.save(update_fields=["journal_entry", "status", "updated_at"])

        return entry

    # =========================================================
    # reverse
    # =========================================================
    @transaction.atomic
    def reverse(self):
        self.validate_for_reverse()

        from apps.accounting.services import create_journal_entry

        amount = Decimal(self.grand_total or 0).quantize(Decimal("0.01"))

        reverse_entry = create_journal_entry(
            entry_date=timezone.localdate(),
            description=f"Invoice reverse {self.invoice_number}",
            source_app="invoices",
            source_model="InvoiceReverse",
            source_id=self.id,
            lines=[
                {
                    "account":     self.revenue_account,
                    "debit":       amount,
                    "credit":      Decimal("0.00"),
                    "description": f"Reverse revenue for invoice {self.invoice_number}",
                },
                {
                    "account":     self.receivable_account,
                    "debit":       Decimal("0.00"),
                    "credit":      amount,
                    "description": f"Reverse receivable for invoice {self.invoice_number}",
                },
            ],
        )

        self.reversed_journal_entry = reverse_entry
        self.status = "reversed"
        self.save(update_fields=["reversed_journal_entry", "status", "updated_at"])

        return reverse_entry

    # =========================================================
    # recalculate_totals
    # =========================================================
    def recalculate_totals(self):
        subtotal  = Decimal("0.00")
        total_tax = Decimal("0.00")

        for item in self.items.all():
            line_subtotal = (
                Decimal(item.quantity or 0) * Decimal(item.unit_price or 0)
            ).quantize(Decimal("0.01"))

            line_tax = (
                line_subtotal * (Decimal(item.tax_percent or 0) / Decimal("100"))
            ).quantize(Decimal("0.01"))

            subtotal  += line_subtotal
            total_tax += line_tax

        self.subtotal   = subtotal.quantize(Decimal("0.01"))
        self.total_tax  = total_tax.quantize(Decimal("0.01"))
        self.grand_total = (self.subtotal + self.total_tax).quantize(Decimal("0.01"))

        self.save(update_fields=["subtotal", "total_tax", "grand_total", "updated_at"])


# =========================================================
# InvoiceItem — بدون تعديل
# =========================================================
class InvoiceItem(models.Model):
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Invoice",
    )

    description = models.CharField(max_length=255, verbose_name="Description")

    quantity = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=Decimal("1.00"), verbose_name="Quantity",
    )

    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal("0.00"), verbose_name="Unit Price",
    )

    tax_percent = models.DecimalField(
        max_digits=5, decimal_places=2,
        default=Decimal("0.00"), verbose_name="Tax Percent",
    )

    line_total = models.DecimalField(
        max_digits=12, decimal_places=2,
        default=Decimal("0.00"), verbose_name="Line Total",
    )

    class Meta:
        verbose_name = "Invoice Item"
        verbose_name_plural = "Invoice Items"

    def __str__(self):
        return self.description

    def clean(self):
        super().clean()
        field_errors = {}

        if self.quantity is not None and Decimal(self.quantity) < 0:
            field_errors["quantity"] = "Quantity cannot be negative."
        if self.unit_price is not None and Decimal(self.unit_price) < 0:
            field_errors["unit_price"] = "Unit price cannot be negative."
        if self.tax_percent is not None and Decimal(self.tax_percent) < 0:
            field_errors["tax_percent"] = "Tax percent cannot be negative."

        if field_errors:
            raise ValidationError(field_errors)

    def save(self, *args, **kwargs):
        if self.invoice_id and not self.invoice.can_edit_core_fields():
            raise ValidationError("لا يمكن تعديل بنود الفاتورة بعد الترحيل أو العكس.")

        self.full_clean()

        line_subtotal = (
            Decimal(self.quantity or 0) * Decimal(self.unit_price or 0)
        ).quantize(Decimal("0.01"))

        line_tax = (
            line_subtotal * (Decimal(self.tax_percent or 0) / Decimal("100"))
        ).quantize(Decimal("0.01"))

        self.line_total = (line_subtotal + line_tax).quantize(Decimal("0.01"))

        result = super().save(*args, **kwargs)
        self.invoice.recalculate_totals()
        return result

    def delete(self, *args, **kwargs):
        if self.invoice_id and not self.invoice.can_edit_core_fields():
            raise ValidationError("لا يمكن حذف بنود الفاتورة بعد الترحيل أو العكس.")

        invoice = self.invoice
        result  = super().delete(*args, **kwargs)
        invoice.recalculate_totals()
        return result
