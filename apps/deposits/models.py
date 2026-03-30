# PATH: apps/deposits/models.py
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from apps.accounting.models import JournalEntry
from apps.rentals.models import Rental


class DepositMethod(models.TextChoices):
    # طرق استلام مبلغ التأمين
    CASH = "cash", "Cash"
    BANK = "bank", "Bank Transfer"
    CARD = "card", "Card"
    CHEQUE = "cheque", "Cheque"


class DepositStatus(models.TextChoices):
    # --- السجل أُنشئ من العقد لكن لم يتم قبضه بعد ---
    PENDING_COLLECTION = "pending_collection", "Pending Collection"

    # --- تم قبض مبلغ التأمين فعليًا ---
    RECEIVED = "received", "Received"

    # --- تم رد جزء من التأمين ---
    PARTIALLY_REFUNDED = "partially_refunded", "Partially Refunded"

    # --- تم رد كامل التأمين ---
    FULLY_REFUNDED = "fully_refunded", "Fully Refunded"


class Deposit(models.Model):
    # العقد المرتبط بهذا التأمين
    rental = models.ForeignKey(
        Rental,
        on_delete=models.PROTECT,
        related_name="deposits",
        verbose_name="Rental Contract",
    )

    # مبلغ التأمين المستلم
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Deposit Amount",
    )

    # تاريخ استلام التأمين
    deposit_date = models.DateField(
        verbose_name="Deposit Date",
    )

    # طريقة استلام مبلغ التأمين
    method = models.CharField(
        max_length=20,
        choices=DepositMethod.choices,
        default=DepositMethod.CASH,
        verbose_name="Method",
    )

    # مرجع مستقل لوثيقة التأمين - سنولده لاحقًا من service وليس من الموديل
    reference = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        verbose_name="Reference",
    )

    # الحالة الحالية للتأمين
    status = models.CharField(
        max_length=30,
        choices=DepositStatus.choices,
        default=DepositStatus.PENDING_COLLECTION,
        verbose_name="Status",
    )

    # القيد المحاسبي الناتج عن استلام التأمين
    journal_entry = models.OneToOneField(
        JournalEntry,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="deposit_record",
        verbose_name="Journal Entry",
    )

    # ملاحظات إضافية
    notes = models.TextField(
        blank=True,
        verbose_name="Notes",
    )

    # تاريخ الإنشاء
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At",
    )

    # تاريخ آخر تعديل
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Updated At",
    )

    class Meta:
        verbose_name = "Deposit"
        verbose_name_plural = "Deposits"
        ordering = ["-deposit_date", "-id"]
        constraints = [
            # منع إدخال مبلغ تأمين صفر أو سالب
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal("0.00")),
                name="deposit_amount_gt_zero",
            ),
        ]
        indexes = [
            # يفيد في الفلترة حسب الحالة داخل الأدمن والتقارير
            models.Index(fields=["status"]),
            # يفيد في الترتيب والبحث الزمني
            models.Index(fields=["deposit_date"]),
        ]

    def __str__(self):
        # إظهار المرجع إن وجد، وإلا إظهار رقم داخلي مؤقت
        return self.reference or f"Deposit #{self.pk}"

    def clean(self):
        super().clean()

        # منع حفظ تأمين بدون عقد
        if not self.rental_id:
            raise ValidationError({"rental": "Rental contract is required."})

        # منع المبالغ الصفرية أو السالبة على مستوى التطبيق أيضًا
        if self.amount is None or self.amount <= 0:
            raise ValidationError(
                {"amount": "Deposit amount must be greater than zero."}
            )

        # لا نسمح بربط أكثر من قيد محاسبي لنفس سجل التأمين بشكل غير مباشر
        if self.journal_entry_id and self.journal_entry.source_model not in [
            None,
            "",
            "Deposit",
        ]:
            raise ValidationError(
                {
                    "journal_entry": "This journal entry is already linked to another source."
                }
            )

    @property
    def refunded_amount(self):
        # مجموع ما تم إرجاعه من هذا التأمين
        return self.refunds.aggregate(total=models.Sum("amount"))["total"] or Decimal(
            "0.00"
        )

    @property
    def remaining_amount(self):
        # الرصيد المتبقي من مبلغ التأمين بعد أي استردادات
        return self.amount - self.refunded_amount


    @property
    def calculated_status(self):
        # --- حاشية عربية: الحالة المشتقة لم تعد تعتمد على أي Refund ---
        # --- طالما لا يوجد قيد قبض فعلي فالسند Pending Collection ---
        if not self.journal_entry_id:
            return DepositStatus.PENDING_COLLECTION

        # --- بمجرد وجود قيد قبض فعلي نعتبر السند Received ---
        return DepositStatus.RECEIVED


    @property
    def calculated_status_display(self):
        # --- حاشية عربية: العرض أصبح محصورًا بحالتين فقط ---
        status_map = {
            DepositStatus.PENDING_COLLECTION: "Pending Collection",
            DepositStatus.RECEIVED: "Received",
        }
        return status_map.get(
            self.calculated_status,
            self.calculated_status.replace("_", " ").title(),
        )

    @property
    def calculated_status_display(self):
        status_map = {
            DepositStatus.PENDING_COLLECTION: "Pending Collection",
            DepositStatus.RECEIVED: "Received",
            DepositStatus.PARTIALLY_REFUNDED: "Partially Refunded",
            DepositStatus.FULLY_REFUNDED: "Fully Refunded",
        }
        return status_map.get(
            self.calculated_status,
            self.calculated_status.replace("_", " ").title(),
        )


class DepositRefund(models.Model):
    # طرق إعادة مبلغ التأمين
    class RefundMethod(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank Transfer"
        CARD = "card", "Card"
        CHEQUE = "cheque", "Cheque"

    # سند التأمين الأصلي المرتبط بهذه الإعادة
    deposit = models.ForeignKey(
        Deposit,
        on_delete=models.PROTECT,
        related_name="refunds",
        verbose_name="Deposit",
    )

    # مبلغ الإعادة
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Refund Amount",
    )

    # تاريخ الإعادة
    refund_date = models.DateField(
        verbose_name="Refund Date",
    )

    # طريقة إعادة المبلغ
    method = models.CharField(
        max_length=20,
        choices=RefundMethod.choices,
        default=RefundMethod.CASH,
        verbose_name="Method",
    )

    # مرجع مستقل لسند الإعادة
    reference = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        verbose_name="Reference",
    )

    # القيد المحاسبي الناتج عن الإعادة
    journal_entry = models.OneToOneField(
        JournalEntry,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="deposit_refund_record",
        verbose_name="Journal Entry",
    )

    # ملاحظات إضافية
    notes = models.TextField(
        blank=True,
        verbose_name="Notes",
    )

    # تواريخ النظام
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Updated At",
    )

    class Meta:
        verbose_name = "Deposit Refund"
        verbose_name_plural = "Deposit Refunds"
        ordering = ["-refund_date", "-id"]
        constraints = [
            # منع إدخال مبلغ صفر أو سالب
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal("0.00")),
                name="deposit_refund_amount_gt_zero",
            ),
        ]
        indexes = [
            models.Index(fields=["refund_date"]),
            models.Index(fields=["deposit"]),
        ]

    def __str__(self):
        return self.reference or f"Deposit Refund #{self.pk}"

    def clean(self):
        super().clean()

        # التأكد من وجود سند التأمين
        if not self.deposit_id:
            raise ValidationError({"deposit": "Deposit is required."})

        # منع مبلغ إرجاع صفر أو سالب
        if self.amount is None or self.amount <= 0:
            raise ValidationError(
                {"amount": "Refund amount must be greater than zero."}
            )

        # عند التعديل نستثني السجل الحالي من المجموع
        previous_refunds = self.deposit.refunds.exclude(pk=self.pk).aggregate(
            total=models.Sum("amount")
        )["total"] or Decimal("0.00")

        # الرصيد المتاح للإعادة = مبلغ التأمين - مجموع الإعادات السابقة
        available_amount = self.deposit.amount - previous_refunds

        # منع إعادة مبلغ أكبر من المتبقي
        if self.amount > available_amount:
            raise ValidationError(
                {
                    "amount": (
                        f"Refund amount cannot exceed remaining deposit amount "
                        f"({available_amount})."
                    )
                }
            )
