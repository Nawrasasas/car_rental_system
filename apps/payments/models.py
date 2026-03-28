# PATH: apps/payments/models.py
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import models, transaction
from apps.rentals.models import Rental

from decimal import Decimal

# موديل الدفعة/سند القبض.
class Payment(models.Model):
    # خيارات حالة السند التشغيلية.
    STATUS_CHOICES = (
        ("completed", "Completed"),
        ("pending", "Pending"),
    )

    # وسائل الدفع المتاحة في السند.
    PAYMENT_METHODS = (
        ("cash", "Cash"),
        ("transfer", "Bank Transfer"),
        ("card", "Card/POS"),
    )

    # حالات الترحيل المحاسبي للسند.
    ACCOUNTING_STATE_CHOICES = (
        ("draft", "Draft"),
        ("posted", "Posted"),
    )

    # المرجع الموحد للسند، ويولد تلقائيًا بصيغة RCT-YYYYMM-0001.
    reference = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        null=True,  # 
        default=None,
        verbose_name="Receipt Reference",
    )

    # حالة السند داخل المحاسبة.
    accounting_state = models.CharField(
        max_length=10,
        choices=ACCOUNTING_STATE_CHOICES,
        default="draft",
        verbose_name="Accounting State",
    )

    # القيد المحاسبي الناتج عن ترحيل سند القبض.
    journal_entry = models.OneToOneField(
        "accounting.JournalEntry",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payment_record",
        verbose_name="Journal Entry",
    )

    # العملية الإيجارية المرتبطة بهذه الدفعة.
    rental = models.ForeignKey(
        Rental,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name="Rental Operation",
    )

    # مبلغ الدفعة المقبوضة.
    amount_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Amount",
    )

    # وسيلة الدفع المستخدمة.
    method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHODS,
        default="cash",
        verbose_name="Payment Method",
    )

    # حالة السند التشغيلية.
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        verbose_name="Status",
    )

    # تاريخ السند.
    payment_date = models.DateField(
        default=timezone.localdate,
        verbose_name="Payment Date",
    )

    # ملاحظات إضافية.
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes",
    )

    class Meta:
        # اسم مفرد داخل الإدارة.
        verbose_name = "Payment"
        # اسم جمع داخل الإدارة.
        verbose_name_plural = "Payments"
        # ترتيب الأحدث أولًا.
        ordering = ["-payment_date", "-id"]

    def __str__(self):
        # عرض المرجع مع المبلغ ليسهل التعرف على السند.
        return f"{self.reference or 'RCT'} - {self.amount_paid}"

    def clean(self):
        # --- نجمع الأخطاء على مستوى الحقول حتى تظهر بشكل صحيح في الأدمن والـ API ---
        errors = {}

        # --- منع المبلغ الصفري أو السالب ---
        if getattr(self, "amount_paid", None) is None or self.amount_paid <= Decimal(
            "0.00"
        ):
            errors["amount_paid"] = "Payment amount must be strictly positive."

        # --- منع حفظ الدفعة بدون طريقة دفع ---
        if not self.method:
            errors["method"] = "Payment method must be specified."

        # --- إذا وُجدت أخطاء نرفعها دفعة واحدة ---
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # --- توليد المرجع تلقائيًا عند أول حفظ فقط ---
        if not self.reference:
            # --- استيراد محلي لتجنب الدوران بين التطبيقات وقت التحميل ---
            from apps.accounting.services import generate_payment_reference

            # --- إنشاء المرجع اعتمادًا على تاريخ السند ---
            self.reference = generate_payment_reference(payment_date=self.payment_date)

        # --- الحفظ هنا يبقى حفظًا فقط بدون أي منطق محاسبي ---
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # --- منع حذف السند إذا كان مرحلًا أو مرتبطًا بقيد ---
        if self.accounting_state == "posted" or self.journal_entry_id:
            raise ValidationError("Posted payments cannot be deleted.")

        # --- إذا لم يكن مرحلًا نسمح بالحذف الطبيعي ---
        return super().delete(*args, **kwargs)


class DepositRefund(models.Model):
    """
    هذا الموديل يمثل حركة إرجاع التأمين للعميل.
    يمكن أن يكون الإرجاع كامل أو جزئي.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("partial", "Partially Refunded"),
        ("refunded", "Refunded"),
        ("withheld", "Withheld"),
    ]

    # --- ربط مع العقد ---
    rental = models.ForeignKey(
        "rentals.Rental",
        on_delete=models.CASCADE,
        related_name="deposit_refunds",
        verbose_name="Rental",
    )

    # --- مبلغ الإرجاع ---
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Refund Amount"
    )

    # --- حالة الإرجاع ---
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="Status"
    )

    # --- تاريخ الإرجاع ---
    refund_date = models.DateTimeField(auto_now_add=True, verbose_name="Refund Date")

    # --- طريقة الإرجاع ---
    method = models.CharField(
        max_length=50,
        choices=[
            ("cash", "Cash"),
            ("bank", "Bank Transfer"),
        ],
        default="cash",
        verbose_name="Method",
    )
    journal_entry = models.OneToOneField(
        "accounting.JournalEntry",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name="Journal Entry",
    )
    # --- ملاحظات ---
    notes = models.TextField(blank=True, verbose_name="Notes")

    # --- بيانات النظام ---
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        errors = {}

        # التحقق من المبلغ
        if self.amount is None or self.amount <= Decimal("0.00"):
            errors["amount"] = "Refund amount must be strictly positive."

        # التحقق من طريقة الدفع
        if not self.method:
            errors["method"] = "Payment method must be specified for a refund."

        # إذا كان هناك أي أخطاء، نرفعها دفعة واحدة لترتبط بالحقول
        if errors:
            raise ValidationError(errors)
            
    def __str__(self):
        return f"Refund #{self.id} - {self.rental}"
