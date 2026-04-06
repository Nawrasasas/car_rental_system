# PATH: apps/exchange_rates/services.py
from decimal import Decimal
from django.utils import timezone


class ExchangeRateNotFound(Exception):
    """يُرفع عندما لا يوجد سعر صرف مسجل للعملة في التاريخ المطلوب أو قبله."""
    pass


def get_exchange_rate(currency_code: str, date=None) -> Decimal:
    """
    تُرجع سعر الصرف المناسب لعملة معينة في تاريخ معين.

    القاعدة:
    - USD دائمًا = Decimal("1") — لا يحتاج بحثًا
    - لأي عملة أخرى: يُبحث عن أحدث سعر مدخل في التاريخ المطلوب أو قبله
    - إذا لم يوجد أي سعر → يُرفع ExchangeRateNotFound

    المعنى: القيمة المُرجعة هي "كم دولار يساوي 1 وحدة من العملة المطلوبة"
    مثال: get_exchange_rate("IQD") = Decimal("0.000769")
    """
    from .models import ExchangeRate

    currency_code = (currency_code or "USD").upper()

    if currency_code == "USD":
        return Decimal("1")

    if date is None:
        date = timezone.localdate()

    rate_obj = (
        ExchangeRate.objects.filter(
            currency_code=currency_code,
            effective_date__lte=date,
        )
        .order_by("-effective_date")
        .first()
    )

    if rate_obj is None:
        raise ExchangeRateNotFound(
            f"No exchange rate found for {currency_code} on or before {date}. "
            f"Please add a rate in Exchange Rates."
        )

    # rate_to_usd هو property محسوب = 1 / units_per_usd
    # هو المضاعف الداخلي: amount_usd = amount_paid * rate_to_usd
    return rate_obj.rate_to_usd


def get_exchange_rate_or_none(currency_code: str, date=None) -> Decimal | None:
    """
    نسخة آمنة من get_exchange_rate تُرجع None بدل رفع استثناء.
    مفيدة في الأدمن والـ JS للعرض فقط.
    """
    try:
        return get_exchange_rate(currency_code, date)
    except ExchangeRateNotFound:
        return None
