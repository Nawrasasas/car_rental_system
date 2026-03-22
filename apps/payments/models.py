from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.rentals.models import Rental


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

    def save(self, *args, **kwargs):
        # توليد المرجع تلقائيًا عند أول حفظ فقط.
        if not self.reference:
            # استيراد محلي لتجنب الدوران بين التطبيقات وقت التحميل.
            from apps.accounting.services import generate_payment_reference

            # إنشاء المرجع اعتمادًا على تاريخ السند.
            self.reference = generate_payment_reference(payment_date=self.payment_date)

        # متابعة الحفظ الطبيعي بعد ضمان وجود المرجع.
        return super().save(*args, **kwargs)

    def post_to_accounting(self):
        # استيراد دالة الترحيل عند الطلب فقط لتجنب الدوران.
        from apps.accounting.services import post_payment_receipt

        # استدعاء خدمة الترحيل وإرجاع نتيجة القيد.
        return post_payment_receipt(payment=self)

    def delete(self, *args, **kwargs):
        # منع حذف السند إذا كان مرحلًا أو مرتبطًا بقيد.
        if self.accounting_state == "posted" or self.journal_entry_id:
            raise ValidationError("Posted payments cannot be deleted.")
        # إذا لم يكن مرحلًا نسمح بالحذف الطبيعي.
        return super().delete(*args, **kwargs)
