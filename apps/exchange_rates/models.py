# PATH: apps/exchange_rates/models.py
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.accounting.models import CurrencyCode


class ExchangeRate(models.Model):
    """
    سعر صرف يومي يُدخله الموظف يدويًا.
    العملة الأساسية دائمًا هي الدولار (USD).
    المعنى: 1 وحدة من العملة المختارة = rate_to_usd دولار.
    مثال: IQD → rate_to_usd = 0.000769 (يعني 1 IQD = 0.000769 USD)
    أو بعبارة أخرى: 1 USD = 1 / 0.000769 ≈ 1300 IQD
    """

    # قائمة العملات غير الدولار فقط - لأن USD دائمًا = 1 ولا يحتاج إدخالاً
    NON_USD_CURRENCIES = [
        (code, label)
        for code, label in CurrencyCode.choices
        if code != CurrencyCode.USD
    ]

    # العملة التي يمثلها هذا السعر
    currency_code = models.CharField(
        max_length=3,
        choices=NON_USD_CURRENCIES,
        verbose_name="Currency",
        db_index=True,
    )

    # كم وحدة محلية تساوي 1 دولار أمريكي
    # هذا هو الاتجاه الطبيعي للإدخال: الموظف يكتب مثلاً 1500 لـ IQD
    # النظام يحسب العكس داخلياً عند الترحيل: rate_to_usd = 1 / units_per_usd
    units_per_usd = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        verbose_name="Units per 1 USD",
        help_text=(
            "How many units of this currency equal 1 USD. "
            "Example: enter 1500 for IQD (meaning 1 USD = 1500 IQD)"
        ),
    )

    # تاريخ سريان هذا السعر - النظام يأخذ أقرب سعر سابق للتاريخ المطلوب
    effective_date = models.DateField(
        default=timezone.localdate,
        verbose_name="Effective Date",
        db_index=True,
    )

    # ملاحظات اختيارية (مثلاً: مصدر السعر)
    notes = models.TextField(
        blank=True,
        verbose_name="Notes",
    )

    # الموظف الذي أدخل السعر
    created_by = models.ForeignKey(
        get_user_model(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exchange_rates_created",
        verbose_name="Created By",
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = "Exchange Rate"
        verbose_name_plural = "Exchange Rates"
        ordering = ["-effective_date", "currency_code"]
        # لا يسمح بإدخال نفس العملة مرتين في نفس اليوم
        unique_together = [("currency_code", "effective_date")]
        indexes = [
            models.Index(fields=["currency_code", "effective_date"]),
        ]

    def __str__(self):
        return (
            f"1 USD = {self.units_per_usd} {self.currency_code}  "
            f"[{self.effective_date}]"
        )

    @property
    def rate_to_usd(self):
        """
        المضاعف الداخلي المستخدم في الحساب المحاسبي:
        كم دولار يساوي 1 وحدة محلية = 1 / units_per_usd
        مثال: إذا 1 USD = 1500 IQD → rate_to_usd = 1/1500 = 0.000667
        """
        if self.units_per_usd and self.units_per_usd > 0:
            return (Decimal("1") / Decimal(self.units_per_usd)).quantize(Decimal("0.000001"))
        return None

    def clean(self):
        errors = {}

        # لا نسمح بإدخال سعر للدولار - هو دائمًا 1
        if self.currency_code == CurrencyCode.USD:
            errors["currency_code"] = (
                "USD is the base currency. Only enter rates for other currencies."
            )

        # القيمة يجب أن تكون أكبر من صفر
        if self.units_per_usd is not None and self.units_per_usd <= Decimal("0"):
            errors["units_per_usd"] = "Value must be greater than zero."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
