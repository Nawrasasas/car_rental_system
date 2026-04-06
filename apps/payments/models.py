# PATH: apps/payments/models.py
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import models, transaction
from apps.rentals.models import Rental
from apps.accounting.models import CurrencyCode
from apps.exchange_rates.models import ExchangeRate
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
        ("bank_transfer", "Bank Transfer"),
        ("visa", "Visa"),
        ("mastercard", "Mastercard"),
        ("pos", "POS / Card"),
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

    # =========================================================
    # بيانات العملة الأصلية للدفعة
    # =========================================================
    # الموظف سيختار العملة فقط من الواجهة لاحقًا
    # أما سعر الصرف والمبلغ بالدولار فسيتم احتسابهما في الخلفية

    # العملة الأصلية التي دُفعت بها العملية
    currency_code = models.CharField(
        max_length=3,
        choices=CurrencyCode.choices,
        default=CurrencyCode.USD,
        verbose_name="Currency",
    )

    # سعر الصرف المستخدم لتحويل الدفعة إلى الدولار
    # يبقى مخزنًا وثابتًا للتاريخ والتقارير بعد الحفظ/الترحيل
    exchange_rate_to_usd = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name="Exchange Rate To USD",
    )

    # تاريخ سعر الصرف المعتمد لهذه الدفعة
    # افتراضيًا سنربطه بتاريخ الدفعة نفسه
    exchange_rate_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Exchange Rate Date",
    )

    # المبلغ المحفوظ بالدولار بعد التحويل
    # هذا هو الرقم الذي سنعتمد عليه لاحقًا في الترحيل والتقارير
    amount_usd = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Amount USD",
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
        errors = {}
        # =====================================================
        # منع ربط الدفعة بعقد غير نشط
        # =====================================================
        rental_status = None
        rental_total = Decimal("0.00")

        if self.rental_id:
            rental_data = (
                Rental.objects.filter(pk=self.rental_id)
                .values("status", "net_total")
                .first()
            )

            if rental_data:
                rental_status = rental_data.get("status")
                rental_total = rental_data.get("net_total") or Decimal("0.00")

                # في نظامنا الحالي:
                # لا نسمح بإنشاء دفعة على عقد مكتمل أو ملغي
                if rental_status in ("cancelled",):
                    errors["rental"] = (
                        "Cannot create a payment for a cancelled rental."
                    )

        # يجب ربط الدفعة بعقد
        if not self.rental_id:
            errors["rental"] = "Payment must be linked to a rental contract."

        # منع المبلغ الصفري أو السالب
        if getattr(self, "amount_paid", None) is None or self.amount_paid <= Decimal("0.00"):
            errors["amount_paid"] = "Payment amount must be strictly positive."

        # منع حفظ الدفعة بدون طريقة دفع
        if not self.method:
            errors["method"] = "Payment method must be specified."

        # منع تجاوز مجموع الدفعات لقيمة العقد
        if (
            self.rental_id
            and getattr(self, "amount_paid", None) is not None
            and self.amount_paid > Decimal("0.00")
        ):
            # نستخدم القيمة التي قرأناها مسبقًا من العقد
            # بدل تنفيذ استعلام ثانٍ
            rental_total = rental_total or Decimal("0.00")

            previous_total = (
                self.__class__.objects.filter(rental_id=self.rental_id)
                .exclude(pk=self.pk)
                .aggregate(total=models.Sum("amount_paid"))["total"]
                or Decimal("0.00")
            )

            new_total = previous_total + Decimal(self.amount_paid)

            if new_total > rental_total:
                remaining_allowed = rental_total - previous_total
                if remaining_allowed < Decimal("0.00"):
                    remaining_allowed = Decimal("0.00")

                errors["amount_paid"] = (
                    f"Payment exceeds contract total. "
                    f"Allowed remaining amount is {remaining_allowed}."
                )
                # =====================================================
        if self.currency_code == CurrencyCode.USD:
            if self.exchange_rate_to_usd is not None and Decimal(
                self.exchange_rate_to_usd
            ) != Decimal("1"):
                errors["exchange_rate_to_usd"] = "USD payments must use exchange rate 1."

        # إذا وُجد Snapshot محفوظ نتأكد فقط أنه موجب
        if self.exchange_rate_to_usd is not None and Decimal(
            self.exchange_rate_to_usd
        ) <= Decimal("0.00"):
            errors["exchange_rate_to_usd"] = "Exchange rate must be greater than zero."

        if self.amount_usd is not None and Decimal(self.amount_usd) < Decimal("0.00"):
            errors["amount_usd"] = "Amount USD cannot be negative."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            # =====================================================
            # قفل العقد لحماية التزامن عند الحفظ
            # =====================================================
            if self.rental_id:
                Rental.objects.select_for_update().only("id").get(pk=self.rental_id)

            # =====================================================
            # تثبيت تاريخ الدفعة وتاريخ سعر الصرف
            # =====================================================
            if not self.payment_date:
                self.payment_date = timezone.localdate()

            if not self.exchange_rate_date:
                self.exchange_rate_date = self.payment_date

            currency_code = (self.currency_code or CurrencyCode.USD).upper()

            # =====================================================
            # Snapshot العملة يُحسب تلقائيًا من Exchange Rates
            # =====================================================
            if currency_code == CurrencyCode.USD:
                # الدولار هو العملة الأساسية
                self.exchange_rate_to_usd = Decimal("1")

                if self.amount_paid is not None:
                    self.amount_usd = Decimal(self.amount_paid).quantize(
                        Decimal("0.01")
                    )
            else:
                # نجلب أحدث سعر صالح في تاريخ الدفعة أو قبله
                rate_obj = (
                    ExchangeRate.objects.filter(
                        currency_code=currency_code,
                        effective_date__lte=self.exchange_rate_date,
                    )
                    .order_by("-effective_date")
                    .first()
                )

                if not rate_obj:
                    raise ValidationError(
                        {
                            "currency_code": (
                                f"No exchange rate found for {currency_code} "
                                f"on or before {self.exchange_rate_date}."
                            )
                        }
                    )

                units_per_usd = Decimal(rate_obj.units_per_usd or 0)

                if units_per_usd <= Decimal("0.00"):
                    raise ValidationError(
                        {"currency_code": "Units per USD must be greater than zero."}
                    )

                # نحفظ الـ snapshot المرجعي للعرض والتقارير
                self.exchange_rate_to_usd = rate_obj.rate_to_usd

                # =================================================
                # الحساب الصحيح للمبلغ المرحّل بالدولار
                # لا نعتمد على الضرب في snapshot المقرب
                # بل نقسم على units_per_usd مباشرةً لتفادي خطأ 600.30
                # =================================================
                if self.amount_paid is not None:
                    self.amount_usd = (
                        Decimal(self.amount_paid) / units_per_usd
                    ).quantize(Decimal("0.01"))

            # =====================================================
            # توليد المرجع تلقائيًا عند أول حفظ فقط
            # =====================================================
            if not self.reference:
                from apps.accounting.services import generate_payment_reference

                self.reference = generate_payment_reference(
                    payment_date=self.payment_date
                )

            # =====================================================
            # تحقق الموديل بعد تجهيز snapshot العملة
            # =====================================================
            self.full_clean()

            return super().save(*args, **kwargs)

    @property
    def refunded_total(self):
        refund = getattr(self, "refund_record", None)
        if refund and refund.journal_entry_id:
            return Decimal(refund.amount or 0)
        return Decimal("0.00")

    @property
    def net_amount_after_refund(self):
        return Decimal(self.amount_paid or 0) - self.refunded_total

    @property
    def is_fully_refunded(self):
        return self.refunded_total >= Decimal(self.amount_paid or 0)


# موديل استرداد الدفعة (مرتبط بسند القبض الأصلي بعلاقة واحد لواحد).
class PaymentRefund(models.Model):
    # سند القبض الأصلي المرتبط بهذا الاسترداد.
    payment = models.OneToOneField(
        Payment,
        on_delete=models.PROTECT,
        related_name="refund_record",
        verbose_name="Original Payment",
    )

    # مبلغ الاسترداد.
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Refund Amount",
    )

    # تاريخ الاسترداد.
    refund_date = models.DateField(
        default=timezone.localdate,
        verbose_name="Refund Date",
    )

    # ملاحظات إضافية.
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Refund Notes",
    )

    # القيد المحاسبي الناتج عن الاسترداد.
    journal_entry = models.OneToOneField(
        "accounting.JournalEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payment_refund_record",
        verbose_name="Refund Journal Entry",
    )

    # تاريخ إنشاء السجل.
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At",
    )

    class Meta:
        verbose_name = "Payment Refund"
        verbose_name_plural = "Payment Refunds"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Refund {self.amount} for {self.payment}"
