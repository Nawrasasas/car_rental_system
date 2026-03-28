# PATH: apps/invoices/models.py
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

# استيراد موديل العميل المعتمد في النظام.
from apps.customers.models import Customer

# استيراد موديل الحساب المحاسبي من التطبيق المعتمد accounting.
from apps.accounting.models import Account, JournalEntry


# موديل الفاتورة الرئيسية.
class Invoice(models.Model):
    # خيارات حالة الفاتورة بعد اعتماد الـ workflow الجديد.
    # ملاحظة:
    # لم نعد نسمح إلا بالحالات الثلاث الأساسية فقط:
    # draft -> posted -> reversed
    STATUS_CHOICES = (
        ("draft", "Draft"),
        ("posted", "Posted"),
        ("reversed", "Reversed"),
    )

    # رقم الفاتورة، ويولد تلقائيًا عند أول حفظ إذا تُرك فارغًا.
    invoice_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        verbose_name="Invoice Number",
    )

    # تاريخ إصدار الفاتورة.
    invoice_date = models.DateField(
        default=timezone.now,
        verbose_name="Invoice Date",
    )

    # تاريخ الاستحقاق إن وجد.
    due_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Due Date",
    )

    # حالة الفاتورة الحالية.
    # افتراضيًا تبدأ دائمًا Draft.
    # في هذه المرحلة نجعل التحكم بها من النظام وليس من الإدخال اليدوي.
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
        verbose_name="Status",
    )

    # اسم الشركة المصدرة للفاتورة.
    from_company = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="From Company",
    )

    # ربط الفاتورة بعميل معرّف مسبقًا داخل النظام.
    # هذا يفيد لاحقًا في التتبع والتسديد والتقارير.
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Customer",
    )

    # الحساب المدين الذي ستحمّل عليه الفاتورة.
    # غالبًا يكون حساب ذمم مدينة أو حساب عميل.
    receivable_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoice_receivable_entries",
        verbose_name="Receivable Account",
    )

    # حساب الإيراد الدائن الذي ستسجل عليه الفاتورة.
    revenue_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoice_revenue_entries",
        verbose_name="Revenue Account",
    )

    # القيد الناتج عن ترحيل الفاتورة عند تنفيذ Post.
    # نربطه بالفاتورة لحفظ الأثر المحاسبي ومنع الترحيل المكرر.
    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="posted_invoices",
        verbose_name="Journal Entry",
        editable=False,
    )

    # القيد العكسي الناتج عن تنفيذ Reverse.
    # هذا يفيد في معرفة أن الفاتورة عُكست بالفعل ومنع عكسها مرتين.
    reversed_journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reversed_invoices",
        verbose_name="Reversed Journal Entry",
        editable=False,
    )

    # اسم العميل.
    customer_name = models.CharField(
        max_length=200,
        verbose_name="Customer Name",
    )

    # بريد العميل الإلكتروني.
    customer_email = models.EmailField(
        blank=True,
        verbose_name="Customer Email",
    )

    # هاتف العميل.
    customer_phone = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Customer Phone",
    )

    # عنوان العميل.
    customer_address = models.TextField(
        blank=True,
        verbose_name="Customer Address",
    )

    # ملاحظات إضافية على الفاتورة.
    notes = models.TextField(
        blank=True,
        verbose_name="Notes",
    )

    # مجموع البنود قبل الضريبة.
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Subtotal",
    )

    # إجمالي الضريبة لكل البنود.
    total_tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Total Tax",
    )

    # الإجمالي النهائي = subtotal + total_tax.
    grand_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Grand Total",
    )

    # تاريخ إنشاء الفاتورة في قاعدة البيانات.
    created_at = models.DateTimeField(auto_now_add=True)
    # تاريخ آخر تعديل على الفاتورة.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # ترتيب الفواتير من الأحدث إلى الأقدم.
        ordering = ["-id"]
        # اسم مفرد داخل الإدارة.
        verbose_name = "Invoice"
        # اسم جمع داخل الإدارة.
        verbose_name_plural = "Invoices"

    def __str__(self):
        # عرض رقم الفاتورة واسم العميل.
        return f"{self.invoice_number or 'INV'} - {self.customer_name}"

    # دالة مساعدة لمعرفة أن الفاتورة ما زالت مسودة.
    def is_draft(self):
        return self.status == "draft"

    # دالة مساعدة لمعرفة أن الفاتورة مرحّلة.
    def is_posted(self):
        return self.status == "posted"

    # دالة مساعدة لمعرفة أن الفاتورة معكوسة.
    def is_reversed(self):
        return self.status == "reversed"


    def validate_for_reverse(self):
        # لا يمكن عكس فاتورة ليست مُرحّلة أصلًا
        if not self.is_posted():
            raise ValidationError("لا يمكن عكس الفاتورة إلا إذا كانت بحالة Posted.")

        # يجب أن يكون هناك قيد أصلي مرتبط بالفاتورة حتى نعكسه
        if not self.journal_entry:
            raise ValidationError("لا يمكن تنفيذ Reverse لأن القيد الأصلي غير موجود.")

        # لا نسمح بالعكس أكثر من مرة
        if self.reversed_journal_entry:
            raise ValidationError("تم إنشاء القيد العكسي مسبقًا لهذه الفاتورة.")

    @transaction.atomic
    def reverse(self):
        # تنفيذ التحقق قبل بدء عملية العكس
        self.validate_for_reverse()

        # استيراد محلي لتجنب أي circular import
        from apps.accounting.models import JournalEntry, JournalEntryLine

        # إنشاء قيد عكسي جديد
        reversed_entry = JournalEntry.objects.create(
            entry_date=timezone.now().date(),
            description=f"Reverse invoice {self.invoice_number}",
            reference=self.invoice_number,
        )

        # المرور على كل سطر من سطور القيد الأصلي
        for line in self.journal_entry.lines.all():
            # إنشاء سطر عكسي:
            # الدائن يصبح مدينًا
            # والمدين يصبح دائنًا
            JournalEntryLine.objects.create(
                journal_entry=reversed_entry,
                account=line.account,
                description=f"Reverse of {line.description or self.invoice_number}",
                debit=line.credit,
                credit=line.debit,
            )

        # ربط القيد العكسي بالفاتورة
        self.reversed_journal_entry = reversed_entry

        # تغيير حالة الفاتورة إلى Reversed
        self.status = "reversed"

        # حفظ الحقول المتغيرة فقط
        self.save(update_fields=["reversed_journal_entry", "status", "updated_at"])

    # تحديد هل يسمح بتعديل الحقول الأساسية أم لا.
    # القاعدة: يسمح فقط في حالة draft.
    def can_edit_core_fields(self):
        return self.is_draft()

    def clean(self):
        # استدعاء تحقق Django القياسي أولًا.
        super().clean()

        # إذا اختير حساب مدين، نتحقق أنه غير موقوف.
        if self.receivable_account and not self.receivable_account.is_active:
            raise ValidationError("الحساب المدين المختار غير نشط.")

        # إذا اختير حساب إيراد، نتحقق أنه غير موقوف.
        if self.revenue_account and not self.revenue_account.is_active:
            raise ValidationError("حساب الإيراد المختار غير نشط.")

        # إذا اختير العميل ولم يُكتب الاسم يدويًا،
        # ننسخ اسمه تلقائيًا إلى الحقل النصي الحالي
        # للمحافظة على التوافق مع التصميم الحالي والطباعة الحالية.
        if self.customer and not self.customer_name:
            self.customer_name = self.customer.full_name

        # نسخ البريد من ملف العميل إن كان موجودًا ولم يُدخل يدويًا.
        if self.customer and not self.customer_email:
            self.customer_email = self.customer.email or ""

        # نسخ الهاتف من ملف العميل إن كان موجودًا ولم يُدخل يدويًا.
        if self.customer and not self.customer_phone:
            self.customer_phone = self.customer.phone or ""

        # نسخ العنوان من ملف العميل إن كان موجودًا ولم يُدخل يدويًا.
        if self.customer and not self.customer_address:
            self.customer_address = self.customer.address or ""

        # في حال كانت الفاتورة خرجت من draft،
        # نمنع تغيير الحسابات الأساسية بعد الترحيل أو العكس.
        if self.pk and not self.can_edit_core_fields():
            original = Invoice.objects.filter(pk=self.pk).first()
            if original:
                changed_after_post = (
                    original.receivable_account_id != self.receivable_account_id
                    or original.revenue_account_id != self.revenue_account_id
                    or original.invoice_date != self.invoice_date
                    or original.customer_id != self.customer_id
                    or original.customer_name != self.customer_name
                    or original.customer_email != self.customer_email
                    or original.customer_phone != self.customer_phone
                    or original.customer_address != self.customer_address
                    or original.from_company != self.from_company
                )
                if changed_after_post:
                    raise ValidationError("لا يمكن تعديل الحقول الأساسية بعد ترحيل الفاتورة أو عكسها.")

    def save(self, *args, **kwargs):
        # معرفة ما إذا كان هذا الحفظ خاصًا فقط بتحديث المجاميع أو الحقول المحاسبية الداخلية.
        update_fields = kwargs.get("update_fields")

        # هذه الحقول يسمح بتحديثها داخليًا بدون إعادة full_clean الكامل.
        internal_safe_update_fields = {
            "subtotal",
            "total_tax",
            "grand_total",
            "updated_at",
            "status",
            "journal_entry",
            "reversed_journal_entry",
        }

        # إذا كان الحفظ داخليًا لحقول محسوبة أو محاسبية فقط،
        # فلا نعيد full_clean حتى لا نمنع عمليات post/reverse نفسها.
        internal_only_update = update_fields is not None and set(update_fields).issubset(
            internal_safe_update_fields
        )

        # ننفذ full_clean فقط في الحفظ الطبيعي للفواتير.
        if not internal_only_update:
            # تنفيذ التحقق والتنظيف قبل الحفظ
            # حتى يتم نسخ بيانات العميل النصية تلقائيًا عند الحاجة.
            self.full_clean()

        # توليد رقم الفاتورة تلقائيًا عند أول حفظ إذا كان الحقل فارغًا.
        if not self.invoice_number:
            # استيراد محلي لتفادي أي تشابك تحميل بين التطبيقات.
            from apps.accounting.services import (
                SequenceResetPolicy,
                generate_sequential_number,
            )

            # إنشاء رقم بصيغة INV-YYYYMM-0001 اعتمادًا على تاريخ الفاتورة.
            self.invoice_number = generate_sequential_number(
                model_class=Invoice,
                field_name="invoice_number",
                prefix="INV",
                doc_date=self.invoice_date,
                reset_policy=SequenceResetPolicy.MONTHLY,
            )

        # تنفيذ الحفظ القياسي بعد التأكد من وجود الرقم.
        return super().save(*args, **kwargs)

    # التحقق من جاهزية الفاتورة للترحيل المحاسبي.
    def validate_for_post(self):
        # لا يمكن ترحيل فاتورة غير محفوظة بعد.
        if not self.pk:
            raise ValidationError("يجب حفظ الفاتورة أولًا قبل الترحيل.")

        # لا نسمح بالترحيل إلا من حالة draft فقط.
        if not self.is_draft():
            raise ValidationError("يمكن ترحيل الفاتورة فقط إذا كانت حالتها draft.")

        # منع تكرار الترحيل إذا كان هناك قيد مرتبط سابقًا.
        if self.journal_entry_id:
            raise ValidationError("هذه الفاتورة مرتبطة أصلًا بقيد محاسبي.")

        # يجب تحديد الحساب المدين قبل الترحيل.
        if not self.receivable_account:
            raise ValidationError("يجب تحديد حساب الذمم قبل ترحيل الفاتورة.")

        # يجب تحديد حساب الإيراد قبل الترحيل.
        if not self.revenue_account:
            raise ValidationError("يجب تحديد حساب الإيراد قبل ترحيل الفاتورة.")

        # لا نسمح بترحيل فاتورة بلا بنود.
        if not self.items.exists():
            raise ValidationError("لا يمكن ترحيل فاتورة بدون بنود.")

        # لا نسمح بترحيل فاتورة بصفر أو أقل.
        if Decimal(self.grand_total or 0) <= Decimal("0.00"):
            raise ValidationError("إجمالي الفاتورة يجب أن يكون أكبر من صفر.")

    # التحقق من جاهزية الفاتورة للعكس المحاسبي.
    def validate_for_reverse(self):
        # لا يمكن عكس فاتورة غير محفوظة.
        if not self.pk:
            raise ValidationError("هذه الفاتورة غير محفوظة بعد.")

        # لا نسمح بالعكس إلا لفاتورة مرحّلة.
        if not self.is_posted():
            raise ValidationError("يمكن عكس الفاتورة فقط إذا كانت حالتها posted.")

        # يجب وجود القيد الأصلي قبل العكس.
        if not self.journal_entry_id:
            raise ValidationError("لا يوجد قيد أصلي مرتبط بهذه الفاتورة لعكسه.")

        # منع العكس المكرر.
        if self.reversed_journal_entry_id:
            raise ValidationError("تم إنشاء القيد العكسي لهذه الفاتورة مسبقًا.")

    # إنشاء القيد الأصلي للفاتورة وتغيير حالتها إلى posted.
    @transaction.atomic
    def post(self):
        # التحقق من الشروط قبل أي حركة محاسبية.
        self.validate_for_post()

        # استيراد محلي لتفادي الدوران بين التطبيقات.
        from apps.accounting.services import create_journal_entry

        # تحويل الإجمالي إلى Decimal بصورة صريحة.
        amount = Decimal(self.grand_total or 0).quantize(Decimal("0.01"))

        # إنشاء القيد المحاسبي من نفس الحسابات المختارة داخل الفاتورة.
        entry = create_journal_entry(
            entry_date=self.invoice_date,
            description=f"Invoice post {self.invoice_number}",
            source_app="invoices",
            source_model="Invoice",
            source_id=self.id,
            lines=[
                {
                    "account": self.receivable_account,
                    "debit": amount,
                    "credit": Decimal("0.00"),
                    "description": f"Receivable for invoice {self.invoice_number}",
                },
                {
                    "account": self.revenue_account,
                    "debit": Decimal("0.00"),
                    "credit": amount,
                    "description": f"Revenue for invoice {self.invoice_number}",
                },
            ],
        )

        # ربط القيد بالفاتورة.
        self.journal_entry = entry
        # تحديث الحالة إلى posted.
        self.status = "posted"
        # حفظ الحقول التي تغيرت فقط.
        self.save(update_fields=["journal_entry", "status", "updated_at"])

        # إعادة القيد الناتج للاستفادة منه في الـ admin أو الخدمات.
        return entry

    # إنشاء القيد العكسي للفواتير المرحّلة وتغيير الحالة إلى reversed.
    @transaction.atomic
    def reverse(self):
        # التحقق من شروط العكس أولًا.
        self.validate_for_reverse()

        # استيراد محلي لتفادي الدوران بين التطبيقات.
        from apps.accounting.services import create_journal_entry

        # تحويل الإجمالي إلى Decimal بصورة صريحة.
        amount = Decimal(self.grand_total or 0).quantize(Decimal("0.01"))

        # إنشاء قيد عكسي يعكس القيد الأصلي:
        # الإيراد يصبح مدينًا، والذمم تصبح دائنة.
        reverse_entry = create_journal_entry(
            entry_date=timezone.localdate(),
            description=f"Invoice reverse {self.invoice_number}",
            source_app="invoices",
            source_model="InvoiceReverse",
            source_id=self.id,
            lines=[
                {
                    "account": self.revenue_account,
                    "debit": amount,
                    "credit": Decimal("0.00"),
                    "description": f"Reverse revenue for invoice {self.invoice_number}",
                },
                {
                    "account": self.receivable_account,
                    "debit": Decimal("0.00"),
                    "credit": amount,
                    "description": f"Reverse receivable for invoice {self.invoice_number}",
                },
            ],
        )

        # ربط القيد العكسي بالفاتورة.
        self.reversed_journal_entry = reverse_entry
        # تحديث الحالة إلى reversed.
        self.status = "reversed"
        # حفظ الحقول التي تغيرت فقط.
        self.save(update_fields=["reversed_journal_entry", "status", "updated_at"])

        # إعادة القيد العكسي الناتج.
        return reverse_entry

    def recalculate_totals(self):
        # متغير لتجميع subtotal من جميع البنود.
        subtotal = Decimal("0.00")
        total_tax = Decimal("0.00")

        # المرور على كل بنود الفاتورة، وليس أول سطر فقط.
        for item in self.items.all():
            # حساب مجموع السطر قبل الضريبة بمنزلتين عشريتين.
            line_subtotal = (
                Decimal(item.quantity or 0) * Decimal(item.unit_price or 0)
            ).quantize(Decimal("0.01"))

            # حساب ضريبة هذا السطر بمنزلتين عشريتين.
            line_tax = (
                line_subtotal * (Decimal(item.tax_percent or 0) / Decimal("100"))
            ).quantize(Decimal("0.01"))

            # جمع جميع السطور في subtotal.
            subtotal += line_subtotal

            # جمع ضرائب جميع السطور.
            total_tax += line_tax

        # تثبيت القيم النهائية مثل العقود تمامًا.
        self.subtotal = subtotal.quantize(Decimal("0.01"))
        self.total_tax = total_tax.quantize(Decimal("0.01"))
        self.grand_total = (self.subtotal + self.total_tax).quantize(Decimal("0.01"))

        # حفظ المجاميع فقط في قاعدة البيانات بدون إعادة full_clean الكامل.
        self.save(update_fields=["subtotal", "total_tax", "grand_total", "updated_at"])


# بند تفصيلي تابع للفاتورة.
class InvoiceItem(models.Model):
    # ربط البند بالفاتورة الأم.
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Invoice",
    )

    # وصف البند أو الخدمة أو المنتج.
    description = models.CharField(
        max_length=255,
        verbose_name="Description",
    )

    # كمية البند.
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1.00"),
        verbose_name="Quantity",
    )

    # سعر الوحدة الواحدة.
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Unit Price",
    )

    # نسبة الضريبة على البند.
    tax_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Tax Percent",
    )

    # إجمالي البند بعد إضافة الضريبة.
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Line Total",
    )

    class Meta:
        # اسم مفرد داخل الإدارة.
        verbose_name = "Invoice Item"
        # اسم جمع داخل الإدارة.
        verbose_name_plural = "Invoice Items"

    def __str__(self):
        # عرض وصف البند.
        return self.description

    def save(self, *args, **kwargs):
        # منع تعديل البنود إذا خرجت الفاتورة من حالة draft.
        if self.invoice_id and not self.invoice.can_edit_core_fields():
            raise ValidationError("لا يمكن تعديل بنود الفاتورة بعد الترحيل أو العكس.")

        # حساب إجمالي البند قبل الضريبة.
        line_subtotal = (
            Decimal(self.quantity or 0) * Decimal(self.unit_price or 0)
        ).quantize(Decimal("0.01"))

        # حساب الضريبة.
        line_tax = (
            line_subtotal * (Decimal(self.tax_percent or 0) / Decimal("100"))
        ).quantize(Decimal("0.01"))

        # إجمالي السطر.
        self.line_total = (line_subtotal + line_tax).quantize(Decimal("0.01"))

        # حفظ البند أولًا حتى يصبح موجودًا فعليًا ضمن عناصر الفاتورة.
        result = super().save(*args, **kwargs)

        # بعد حفظ البند، نعيد حساب مجاميع الفاتورة الأم مباشرة.
        self.invoice.recalculate_totals()

        # إعادة نتيجة الحفظ القياسية.
        return result

    def delete(self, *args, **kwargs):
        # منع حذف البنود إذا خرجت الفاتورة من حالة draft.
        if self.invoice_id and not self.invoice.can_edit_core_fields():
            raise ValidationError("لا يمكن حذف بنود الفاتورة بعد الترحيل أو العكس.")

        # نحتفظ بمرجع الفاتورة قبل حذف البند.
        invoice = self.invoice

        # تنفيذ الحذف القياسي أولًا.
        result = super().delete(*args, **kwargs)

        # بعد حذف البند، نعيد حساب مجاميع الفاتورة حتى لا تبقى القيم القديمة محفوظة.
        invoice.recalculate_totals()

        # إعادة نتيجة الحذف القياسية.
        return result
