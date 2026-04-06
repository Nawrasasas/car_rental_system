from decimal import Decimal
from apps.traffic_fines.services import create_traffic_fine_from_rental
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from apps.exchange_rates.services import get_exchange_rate, ExchangeRateNotFound

from .models import (
    Account,
    AccountType,
    EntryState,
    Expense,
    ExpenseCategory,
    JournalEntry,
    JournalItem,
    PaymentMethod,
    Revenue,
)


# استثناء مخصص لأخطاء المحاسبة ليسهل التقاطه داخل الـ admin أو الخدمات.
class AccountingError(ValidationError):
    pass


# أكواد الحسابات المرجعية المستخدمة في الترحيل الآلي.
class AccountCodes:
    # صندوق / نقدية بالدولار - العملة الأساسية.
    CASH = "1110"

    # صندوق / نقدية بالدينار العراقي.
    CASH_IQD = "1115"

    # بنك / تحويل.
    BANK = "1120"

    # POS / بطاقة ائتمانية.
    POS = "1130"

    # ذمم مدينة / العملاء.
    RENTAL_RECEIVABLES = "1201"

    # ذمم المخالفات المرورية على الزبائن
    CUSTOMER_TRAFFIC_FINES_RECEIVABLE = "1202"

    # التزام للحكومة عن المخالفات المرورية
    GOVERNMENT_TRAFFIC_FINES_PAYABLE = "2600"

    # --- دفعات الإيجار المقدمة قبل ترحيل العقد ---
    RENTAL_ADVANCES = "2120"

    CUSTOMER_DEPOSIT = "2110"
    # إيراد الإيجار.
    RENTAL_REVENUE = "4100"
    # مصروف الصيانة.
    MAINTENANCE_EXPENSE = "3200"
    # مصروف الوقود.
    FUEL_EXPENSE = "3100"
    # مصروف الرواتب.
    SALARY_EXPENSE = "3300"
    # مصروفات أخرى.
    OTHER_EXPENSE = "3900"


# سياسات إعادة ضبط التسلسل حسب اليوم أو الشهر أو السنة.
class SequenceResetPolicy:
    # إعادة التسلسل يوميًا.
    DAILY = "daily"
    # إعادة التسلسل شهريًا.
    MONTHLY = "monthly"
    # إعادة التسلسل سنويًا.
    YEARLY = "yearly"


# طول الجزء التسلسلي الأخير مثل 0001.
DOCUMENT_NUMBER_PADDING = 4


# تحويل أي قيمة رقمية إلى Decimal بصورة آمنة.
def to_decimal(value):
    # في حال كانت القيمة فارغة نعيد صفرًا عشريًا.
    if value is None:
        return Decimal("0.00")

    # إذا كانت القيمة أصلًا Decimal نعيدها كما هي.
    if isinstance(value, Decimal):
        return value

    # تحويل بقية الأنواع إلى Decimal عبر النص لتقليل أخطاء الدقة.
    return Decimal(str(value))


def convert_to_usd_snapshot(*, original_amount, currency_code="USD", rate_date=None):
    """
    تحويل مبلغ من العملة الأصلية إلى الدولار مع إرجاع لقطة كاملة
    تُستخدم مباشرة في create_journal_entry.
    """
    normalized_original_amount = to_decimal(original_amount)
    normalized_currency_code = (currency_code or "USD").upper()
    normalized_rate_date = _normalize_date(rate_date)

    if normalized_original_amount <= 0:
        return {
            "original_currency_code": normalized_currency_code,
            "original_amount": normalized_original_amount,
            "exchange_rate_to_usd": (
                Decimal("1") if normalized_currency_code == "USD" else None
            ),
            "exchange_rate_date": normalized_rate_date,
            "posted_amount_usd": Decimal("0.00"),
        }

    try:
        exchange_rate_to_usd = get_exchange_rate(
            normalized_currency_code,
            normalized_rate_date,
        )
    except ExchangeRateNotFound as exc:
        raise AccountingError(str(exc)) from exc

    posted_amount_usd = (normalized_original_amount * exchange_rate_to_usd).quantize(
        Decimal("0.01")
    )

    return {
        "original_currency_code": normalized_currency_code,
        "original_amount": normalized_original_amount,
        "exchange_rate_to_usd": exchange_rate_to_usd,
        "exchange_rate_date": normalized_rate_date,
        "posted_amount_usd": posted_amount_usd,
    }


# جلب حساب نشط من شجرة الحسابات اعتمادًا على الكود.
def get_account(code: str) -> Account:
    try:
        # محاولة جلب الحساب النشط بالكود المطلوب.
        return Account.objects.get(code=code, is_active=True)
    except Account.DoesNotExist as exc:
        # رفع خطأ محاسبي واضح إذا لم يوجد الحساب.
        raise AccountingError(f"Account with code '{code}' does not exist.") from exc


# تحويل أي تاريخ/وقت وارد إلى date فقط.
def _normalize_date(value):
    # عند عدم تمرير قيمة نستخدم تاريخ اليوم المحلي.
    if value is None:
        return timezone.localdate()

    # إذا كانت القيمة datetime فنحاول استخراج date منها.
    if hasattr(value, "date"):
        try:
            return value.date()
        except TypeError:
            # بعض الأنواع قد تملك date كخاصية غير قابلة للاستدعاء، فنكمل إلى السطر التالي.
            pass

    # إذا كانت القيمة أصلًا date نعيدها كما هي.
    return value


# بناء الجزء الأول من الرقم قبل التسلسل الأخير.
def build_reference_prefix(*, prefix: str, doc_date, reset_policy: str) -> str:
    # توحيد التاريخ إلى قيمة date.
    normalized_date = _normalize_date(doc_date)

    # عند اختيار إعادة يومية نستخدم YYYYMMDD.
    if reset_policy == SequenceResetPolicy.DAILY:
        period_key = normalized_date.strftime("%Y%m%d")
    # عند اختيار إعادة شهرية نستخدم YYYYMM.
    elif reset_policy == SequenceResetPolicy.MONTHLY:
        period_key = normalized_date.strftime("%Y%m")
    # عند اختيار إعادة سنوية نستخدم YYYY.
    elif reset_policy == SequenceResetPolicy.YEARLY:
        period_key = normalized_date.strftime("%Y")
    else:
        # أي سياسة غير معروفة تعتبر خطأ برمجيًا/إعداديًا.
        raise AccountingError(f"Unsupported reset policy: {reset_policy}")

    # إعادة الناتج مثل INV-202603 أو JV-20260320.
    return f"{prefix}-{period_key}"


# مولد عام وموحد للأرقام التسلسلية لكل المستندات.
@transaction.atomic
def generate_sequential_number(*, model_class, field_name: str, prefix: str, doc_date, reset_policy: str) -> str:
    # بناء المقدمة الزمنية للرقم.
    base_prefix = build_reference_prefix(
        prefix=prefix,
        doc_date=doc_date,
        reset_policy=reset_policy,
    )

    # جلب آخر رقم مستخدم داخل نفس الفترة مع قفل الصفوف لتقليل التكرار بالتوازي.
    last_value = (
        model_class.objects.select_for_update()
        .filter(**{f"{field_name}__startswith": f"{base_prefix}-"})
        .order_by(f"-{field_name}")
        .values_list(field_name, flat=True)
        .first()
    )

    # البداية الافتراضية للتسلسل.
    next_sequence = 1

    # إذا وجد رقم سابق نستخرج الجزء الأخير ونزيده واحدًا.
    if last_value:
        try:
            next_sequence = int(str(last_value).rsplit("-", 1)[-1]) + 1
        except (TypeError, ValueError) as exc:
            raise AccountingError(
                f"Unable to parse the last sequence number from '{last_value}'."
            ) from exc

    # إعادة الرقم النهائي بالشكل المطلوب مثل EXP-202603-0001.
    return f"{base_prefix}-{next_sequence:0{DOCUMENT_NUMBER_PADDING}d}"


# توليد رقم قيد يومية بصيغة JV-YYYYMMDD-0001.
def generate_entry_no(entry_date=None) -> str:
    # استخدام موديل القيد الرئيسي مع إعادة يومية.
    return generate_sequential_number(
        model_class=JournalEntry,
        field_name="entry_no",
        prefix="JV",
        doc_date=entry_date or timezone.localdate(),
        reset_policy=SequenceResetPolicy.DAILY,
    )


# توليد رقم مصروف بصيغة EXP-YYYYMM-0001.
def generate_expense_reference(expense_date=None) -> str:
    # استخدام موديل المصروف مع إعادة شهرية.
    return generate_sequential_number(
        model_class=Expense,
        field_name="reference",
        prefix="EXP",
        doc_date=expense_date or timezone.localdate(),
        reset_policy=SequenceResetPolicy.MONTHLY,
    )


# توليد رقم إيراد حالي بصيغة REV-YYYYMM-0001.
def generate_revenue_reference(revenue_date=None) -> str:
    # استخدام موديل الإيراد الحالي مع إعادة شهرية.
    return generate_sequential_number(
        model_class=Revenue,
        field_name="reference",
        prefix="REV",
        doc_date=revenue_date or timezone.localdate(),
        reset_policy=SequenceResetPolicy.MONTHLY,
    )


# توليد رقم سند قبض/دفعة بصيغة RCT-YYYYMM-0001.
def generate_payment_reference(payment_date=None) -> str:
    # الاستيراد داخل الدالة لتفادي الدوران بين accounting و payments.
    from apps.payments.models import Payment

    # استخدام موديل الدفعات مع إعادة شهرية.
    return generate_sequential_number(
        model_class=Payment,
        field_name="reference",
        prefix="RCT",
        doc_date=payment_date or timezone.localdate(),
        reset_policy=SequenceResetPolicy.MONTHLY,
    )


# إنشاء قيد يومية متوازن مع عناصره ثم ترحيله مباشرة.
@transaction.atomic
def create_journal_entry(
    *,
    entry_date,
    description,
    lines,
    source_app="",
    source_model="",
    source_id=None,
    # =========================================================
    # حقول مرجعية جديدة لحفظ أصل العملية بعملتها الأصلية
    # =========================================================
    original_currency_code=None,
    original_amount=None,
    exchange_rate_to_usd=None,
    exchange_rate_date=None,
    posted_amount_usd=None,
):
    # =========================================================
    # تجهيز القيم المرجعية قبل إنشاء القيد
    # =========================================================
    # حاشية:
    # هذه القيم لا تغيّر منطق المدين/الدائن
    # وإنما تُحفظ على رأس القيد فقط لعرض أصل العملية لاحقًا
    normalized_entry_date = _normalize_date(entry_date)

    # إذا لم تُرسل عملة أصلية نعتبرها USD افتراضيًا
    normalized_original_currency_code = original_currency_code or "USD"

    # تحويل القيم الرقمية إلى Decimal بصورة آمنة عند وجودها
    normalized_original_amount = (
        to_decimal(original_amount) if original_amount is not None else None
    )
    normalized_exchange_rate_to_usd = (
        to_decimal(exchange_rate_to_usd) if exchange_rate_to_usd is not None else None
    )
    normalized_posted_amount_usd = (
        to_decimal(posted_amount_usd) if posted_amount_usd is not None else None
    )

    # إذا لم يُرسل تاريخ سعر الصرف نستخدم تاريخ القيد نفسه
    normalized_exchange_rate_date = (
        _normalize_date(exchange_rate_date)
        if exchange_rate_date
        else normalized_entry_date
    )

    # إذا كانت العملة الأصلية USD ولم يُرسل سعر صرف
    # نثبّت السعر 1 تلقائيًا
    if (
        normalized_original_currency_code == "USD"
        and normalized_exchange_rate_to_usd is None
    ):
        normalized_exchange_rate_to_usd = Decimal("1")

    # إذا أُرسل مبلغ أصلي ولم يُرسل posted_amount_usd
    # وكان لدينا سعر صرف صالح، نحسب الدولار تلقائيًا
    if (
        normalized_original_amount is not None
        and normalized_posted_amount_usd is None
        and normalized_exchange_rate_to_usd is not None
    ):
        normalized_posted_amount_usd = (
            normalized_original_amount * normalized_exchange_rate_to_usd
        ).quantize(Decimal("0.01"))

    # إنشاء رأس القيد بحالة مسودة أولًا.
    entry = JournalEntry.objects.create(
        entry_no=generate_entry_no(entry_date=normalized_entry_date),
        entry_date=normalized_entry_date,
        description=description,
        source_app=source_app,
        source_model=source_model,
        source_id=source_id,
        state=EntryState.DRAFT,
        # =====================================================
        # حفظ مرجع أصل العملية على رأس القيد
        # =====================================================
        original_currency_code=normalized_original_currency_code,
        original_amount=normalized_original_amount,
        exchange_rate_to_usd=normalized_exchange_rate_to_usd,
        exchange_rate_date=normalized_exchange_rate_date,
        posted_amount_usd=normalized_posted_amount_usd,
    )

    # متغير لتجميع إجمالي المدين.
    total_debit = Decimal("0.00")
    # متغير لتجميع إجمالي الدائن.
    total_credit = Decimal("0.00")

    # إنشاء كل سطر من الأسطر المرسلة.
    for line in lines:
        # الحساب الخاص بالسطر الحالي.
        account = line["account"]
        # قيمة المدين بعد تحويلها إلى Decimal.
        debit = to_decimal(line.get("debit", 0))
        # قيمة الدائن بعد تحويلها إلى Decimal.
        credit = to_decimal(line.get("credit", 0))
        # وصف السطر إن وجد.
        line_description = line.get("description", "")

        # إنشاء عنصر القيد.
        JournalItem.objects.create(
            journal_entry=entry,
            account=account,
            description=line_description,
            debit=debit,
            credit=credit,
        )

        # تحديث الإجماليات بعد كل سطر.
        total_debit += debit
        total_credit += credit

    # التحقق النهائي من توازن القيد قبل اعتماد القيد.
    if total_debit != total_credit:
        raise AccountingError(
            f"Unbalanced journal entry. Debit={total_debit}, Credit={total_credit}"
        )

    # =========================================================
    # إذا لم يُرسل posted_amount_usd صراحة
    # نثبّت الإجمالي المحاسبي الفعلي من السطور
    # =========================================================
    # حاشية:
    # بما أن القيد متوازن، فإن total_debit == total_credit
    # لذلك نستخدم total_debit كمرجع نهائي للمبلغ المرحّل بالدولار
    if entry.posted_amount_usd is None:
        entry.posted_amount_usd = total_debit.quantize(Decimal("0.01"))
        entry.save(update_fields=["posted_amount_usd", "updated_at"])

    # نمرر الترحيل من دالة post() داخل الموديل حتى يبقى منطق الترحيل في مكان واحد
    # هذا يضمن تعبئة posted_at وتطبيق التحقق والقفل بنفس المسار الرسمي
    entry.post()

    # نعيد تحميل القيم المحدثة من قاعدة البيانات حتى يبقى الكائن متزامنًا
    entry.refresh_from_db(
        fields=["state", "posted_at", "updated_at", "posted_amount_usd"]
    )

    # إعادة القيد الناتج لاستخدامه في ربط المصدر.
    return entry


# تحديد حساب الصندوق أو البنك حسب وسيلة الدفع والعملة.
def get_cash_or_bank_account(payment_method: str, currency_code: str = "USD") -> Account:
    """
    يُرجع الحساب المناسب حسب وسيلة الدفع والعملة.

    - النقدية بالدولار  → 1110 Cash (USD)
    - النقدية بالدينار  → 1115 Cash - Iraqi Dinar (IQD)
    - POS              → 1130 بغض النظر عن العملة
    - البنك / Visa / Mastercard → 1120

    ملاحظة: المبلغ في سطور القيد دائمًا بالدولار بعد التحويل.
    الحساب وحده هو الذي يتغير لتتبع مصدر النقد فعلياً.
    """
    method = (payment_method or "").lower()
    currency = (currency_code or "USD").upper()

    # النقدية: نحدد الصندوق حسب العملة
    if method in [PaymentMethod.CASH, "cash"]:
        if currency == "IQD":
            return get_account(AccountCodes.CASH_IQD)
        return get_account(AccountCodes.CASH)

    # POS / بطاقة ائتمانية → حساب POS المنفصل
    if method in ["pos"]:
        return get_account(AccountCodes.POS)

    # البنك / التحويل / Visa / Mastercard → حساب البنك
    if method in [
        PaymentMethod.TRANSFER, PaymentMethod.CARD,
        "transfer", "card", "bank",
        "bank_transfer", "visa", "mastercard",
    ]:
        return get_account(AccountCodes.BANK)

    # أي قيمة أخرى غير مدعومة تعتبر خطأ واضحًا.
    raise AccountingError(f"Unsupported payment method: {payment_method}")


# تحديد حساب المصروف المناسب حسب التصنيف.
def get_expense_account_by_category(category: str) -> Account:
    # الصيانة.
    if category == ExpenseCategory.MAINTENANCE:
        return get_account(AccountCodes.MAINTENANCE_EXPENSE)

    # الوقود.
    if category == ExpenseCategory.FUEL:
        return get_account(AccountCodes.FUEL_EXPENSE)

    # الرواتب.
    if category == ExpenseCategory.SALARY:
        return get_account(AccountCodes.SALARY_EXPENSE)

    # أي شيء آخر يذهب إلى مصروفات أخرى.
    return get_account(AccountCodes.OTHER_EXPENSE)


# ترحيل إيراد عقد الإيجار كذمة على العميل.


@transaction.atomic
@transaction.atomic
def post_rental_revenue(*, rental):
    from apps.payments.models import Payment

    # --- قفل العقد من قاعدة البيانات لمنع الترحيل المكرر المتوازي ---
    locked_rental = rental.__class__.objects.select_for_update().get(pk=rental.pk)

    # --- منع الترحيل إذا كان هناك قيد مرتبط مسبقًا ---
    if getattr(locked_rental, "journal_entry_id", None):
        raise AccountingError("This rental is already posted to accounting.")

    # --- منع الترحيل إذا كانت الحالة المحاسبية posted مسبقًا ---
    if getattr(locked_rental, "accounting_state", "draft") == EntryState.POSTED:
        raise AccountingError("This rental accounting state is already posted.")

    # =========================================================
    # قراءة مبالغ العقد بعملتها الأصلية كما أُدخلت على شاشة العقد
    # =========================================================
    total_amount_original = to_decimal(getattr(locked_rental, "net_total", 0))
    traffic_fines_original = to_decimal(getattr(locked_rental, "traffic_fines", 0))
    deposit_amount_original = to_decimal(getattr(locked_rental, "deposit_amount", 0))

    # --- قيد العقد الأساسي فقط ---
    # --- نستبعد المخالفة والتأمين لأن لكل واحد مساره المستقل ---
    rental_amount_original = (
        total_amount_original - traffic_fines_original - deposit_amount_original
    )

    if rental_amount_original <= 0:
        raise AccountingError("Rental amount must be greater than zero.")

    # =========================================================
    # تحديد العملة الأصلية وتاريخ سعر الصرف للعقد
    # نعتمد تاريخ بداية العقد كسجل تاريخي لأصل العملية
    # =========================================================
    original_currency_code = getattr(locked_rental, "currency_code", "USD") or "USD"
    exchange_rate_date = _normalize_date(
        getattr(locked_rental, "start_date", None) or timezone.now().date()
    )

    rental_snapshot = convert_to_usd_snapshot(
        original_amount=rental_amount_original,
        currency_code=original_currency_code,
        rate_date=exchange_rate_date,
    )
    rental_amount_usd = rental_snapshot["posted_amount_usd"]

    traffic_fine_snapshot = None
    traffic_fines_usd = Decimal("0.00")
    if traffic_fines_original > Decimal("0.00"):
        traffic_fine_snapshot = convert_to_usd_snapshot(
            original_amount=traffic_fines_original,
            currency_code=original_currency_code,
            rate_date=exchange_rate_date,
        )
        traffic_fines_usd = traffic_fine_snapshot["posted_amount_usd"]

    # --- حسابات الإيجار ---
    receivable_account = get_account(AccountCodes.RENTAL_RECEIVABLES)  # 1201
    revenue_account = get_account(AccountCodes.RENTAL_REVENUE)  # 4100

    # --- حسابات المخالفات ---
    traffic_fines_receivable_account = get_account(
        AccountCodes.CUSTOMER_TRAFFIC_FINES_RECEIVABLE
    )  # 1202
    traffic_fines_payable_account = get_account(
        AccountCodes.GOVERNMENT_TRAFFIC_FINES_PAYABLE
    )  # 2600

    # --- حساب دفعات الإيجار المقدمة قبل الترحيل ---
    rental_advances_account = get_account(AccountCodes.RENTAL_ADVANCES)  # 2120

    contract_ref = locked_rental.contract_number or f"Rental #{locked_rental.id}"

    # =========================================================
    # 1) قيد العقد الأساسي بالدولار فقط
    # لكن مع حفظ أصل العملية وسعر الصرف على رأس القيد
    # =========================================================
    entry = create_journal_entry(
        entry_date=exchange_rate_date,
        description=f"Rental revenue for contract {contract_ref}",
        source_app="rentals",
        source_model="Rental",
        source_id=locked_rental.id,
        original_currency_code=rental_snapshot["original_currency_code"],
        original_amount=rental_snapshot["original_amount"],
        exchange_rate_to_usd=rental_snapshot["exchange_rate_to_usd"],
        exchange_rate_date=rental_snapshot["exchange_rate_date"],
        posted_amount_usd=rental_snapshot["posted_amount_usd"],
        lines=[
            {
                # --- إثبات ذمة العميل بالدولار المحاسبي ---
                "account": receivable_account,
                "debit": rental_amount_usd,
                "credit": Decimal("0.00"),
                "description": f"Accounts receivable for contract {contract_ref}",
            },
            {
                # --- إثبات إيراد العقد بالدولار المحاسبي ---
                "account": revenue_account,
                "debit": Decimal("0.00"),
                "credit": rental_amount_usd,
                "description": f"Rental revenue for contract {contract_ref}",
            },
        ],
    )

    # =========================================================
    # 2) قيد المخالفة مستقل عن قيد العقد
    # والمبالغ داخله أيضًا بالدولار بعد التحويل
    # =========================================================
    if traffic_fines_original > Decimal("0.00"):
        create_journal_entry(
            entry_date=exchange_rate_date,
            description=f"Traffic fine for contract {contract_ref}",
            source_app="traffic_fines",
            source_model="TrafficFine",
            source_id=locked_rental.id,
            original_currency_code=traffic_fine_snapshot["original_currency_code"],
            original_amount=traffic_fine_snapshot["original_amount"],
            exchange_rate_to_usd=traffic_fine_snapshot["exchange_rate_to_usd"],
            exchange_rate_date=traffic_fine_snapshot["exchange_rate_date"],
            posted_amount_usd=traffic_fine_snapshot["posted_amount_usd"],
            lines=[
                {
                    # --- ذمة مخالفة على الزبون بالدولار ---
                    "account": traffic_fines_receivable_account,
                    "debit": traffic_fines_usd,
                    "credit": Decimal("0.00"),
                    "description": f"Traffic fine receivable for contract {contract_ref}",
                },
                {
                    # --- التزام للحكومة بالدولار ---
                    "account": traffic_fines_payable_account,
                    "debit": Decimal("0.00"),
                    "credit": traffic_fines_usd,
                    "description": f"Government traffic fine payable for contract {contract_ref}",
                },
            ],
        )

    # --- ربط قيد الإثبات بالعقد كما كان سابقًا ---
    updated_rows = rental.__class__.objects.filter(
        pk=locked_rental.pk,
        journal_entry__isnull=True,
        accounting_state=EntryState.DRAFT,
    ).update(
        journal_entry=entry,
        accounting_state=EntryState.POSTED,
    )

    if updated_rows != 1:
        raise AccountingError("Concurrent posting detected for this rental.")

    rental.journal_entry = entry
    rental.accounting_state = EntryState.POSTED

    # --- إنشاء سجل مخالفة داخل تطبيق traffic_fines فقط إذا كان مبلغ المخالفة موجوداً ---
    if traffic_fines_original > Decimal("0.00"):
        create_traffic_fine_from_rental(rental=locked_rental)

    # =========================================================
    # تجميع الدفعات السابقة بالدولار المحاسبي
    # =========================================================
    advance_total_usd = Decimal("0.00")

    posted_payments = Payment.objects.filter(
        rental_id=locked_rental.id,
        status="completed",
        accounting_state=EntryState.POSTED,
    ).only("amount_usd", "amount_paid")

    for posted_payment in posted_payments:
        payment_amount_usd = getattr(posted_payment, "amount_usd", None)

        if payment_amount_usd is not None:
            advance_total_usd += to_decimal(payment_amount_usd)
        else:
            # --- توافق مؤقت فقط مع السجلات القديمة ---
            advance_total_usd += to_decimal(getattr(posted_payment, "amount_paid", 0))

    # --- التسوية يجب أن تُقارن مع مبلغ العقد بالدولار لا بالعملة الأصلية ---
    settlement_amount_usd = min(advance_total_usd, rental_amount_usd)

    if settlement_amount_usd > 0:
        create_journal_entry(
            entry_date=exchange_rate_date,
            description=f"Apply customer advances to contract {contract_ref}",
            source_app="rentals",
            source_model="RentalAdvanceSettlement",
            source_id=locked_rental.id,
            original_currency_code="USD",
            original_amount=settlement_amount_usd,
            exchange_rate_to_usd=Decimal("1"),
            exchange_rate_date=exchange_rate_date,
            posted_amount_usd=settlement_amount_usd,
            lines=[
                {
                    # --- إقفال التزام العربون السابق ---
                    "account": rental_advances_account,
                    "debit": settlement_amount_usd,
                    "credit": Decimal("0.00"),
                    "description": f"Apply customer advance to contract {contract_ref}",
                },
                {
                    # --- تخفيض ذمة العميل بنفس المبلغ ---
                    "account": receivable_account,
                    "debit": Decimal("0.00"),
                    "credit": settlement_amount_usd,
                    "description": f"Settle receivable using customer advance for contract {contract_ref}",
                },
            ],
        )

    return entry


@transaction.atomic
def post_payment_receipt(*, payment):
    # --- قفل السند من قاعدة البيانات لمنع الترحيل المكرر بالتوازي ---
    locked_payment = (
        payment.__class__.objects.select_for_update()
        .select_related("rental")
        .get(pk=payment.pk)
    )

    # --- منع الترحيل إذا كان هناك قيد مرتبط مسبقًا ---
    if getattr(locked_payment, "journal_entry_id", None):
        raise AccountingError("This payment is already posted to accounting.")

    # --- منع الترحيل إذا كانت الحالة المحاسبية posted ---
    if getattr(locked_payment, "accounting_state", "draft") == EntryState.POSTED:
        raise AccountingError("This payment accounting state is already posted.")

    # --- لا يسمح بترحيل دفعة غير مكتملة ---
    payment_status = getattr(locked_payment, "status", "")
    if payment_status != "completed":
        raise AccountingError("Only completed payments can be posted.")

    # =========================================================
    # قراءة مبلغ الدفعة بصورتين:
    # 1) المبلغ الأصلي بعملة العملية
    # 2) المبلغ المعتمد محاسبيًا بالدولار
    # =========================================================
    original_amount = to_decimal(getattr(locked_payment, "amount_paid", 0))
    if original_amount <= 0:
        raise AccountingError("Payment amount must be greater than zero.")

    original_currency_code = getattr(locked_payment, "currency_code", "USD") or "USD"
    exchange_rate_to_usd = getattr(locked_payment, "exchange_rate_to_usd", None)
    exchange_rate_date = (
        getattr(locked_payment, "exchange_rate_date", None)
        or getattr(locked_payment, "payment_date", None)
        or timezone.now().date()
    )

    # --- إذا كانت قيمة amount_usd محفوظة نستخدمها ---
    # --- وإلا نرجع مؤقتًا إلى amount_paid للحفاظ على التوافق مع السجلات القديمة ---
    amount_usd = getattr(locked_payment, "amount_usd", None)
    if amount_usd is not None:
        amount_usd = to_decimal(amount_usd)
    else:
        amount_usd = original_amount

    if amount_usd <= 0:
        raise AccountingError("Posted USD amount must be greater than zero.")

    # --- تحديد الحساب المدين: كاش أو بنك (مع مراعاة العملة لتوجيه IQD لصندوق منفصل) ---
    cash_or_bank_account = get_cash_or_bank_account(
        getattr(locked_payment, "method", ""),
        currency_code=original_currency_code,
    )

    # --- قراءة العقد المرتبط ---
    rental = getattr(locked_payment, "rental", None)
    if not rental:
        raise AccountingError("Payment must be linked to a rental contract.")

    # --- إذا العقد ما زال Draft => الدفعة تعتبر Rental Advance ---
    # --- إذا العقد Posted => الدفعة تعتبر سدادًا على الذمم ---
    if getattr(rental, "accounting_state", "draft") == EntryState.POSTED and getattr(
        rental, "journal_entry_id", None
    ):
        credit_account = get_account(AccountCodes.RENTAL_RECEIVABLES)
        credit_description = f"Settlement of receivable for rental #{rental.id}"
    else:
        credit_account = get_account(AccountCodes.RENTAL_ADVANCES)
        credit_description = f"Rental advance received for draft rental #{rental.id}"

    rental_id = getattr(locked_payment, "rental_id", None)
    payment_date = (
        getattr(locked_payment, "payment_date", None) or timezone.now().date()
    )
    payment_reference = (
        getattr(locked_payment, "reference", None) or f"PAY-{locked_payment.id}"
    )

    # --- إنشاء القيد بالمبلغ الدولار فقط داخل السطور ---
    # --- مع حفظ مرجع أصل العملية على رأس القيد ---
    entry = create_journal_entry(
        entry_date=payment_date,
        description=f"Customer payment {payment_reference} for rental #{rental_id}",
        source_app="payments",
        source_model="Payment",
        source_id=locked_payment.id,
        # =====================================================
        # حفظ أصل العملية على رأس القيد
        # =====================================================
        original_currency_code=original_currency_code,
        original_amount=original_amount,
        exchange_rate_to_usd=exchange_rate_to_usd,
        exchange_rate_date=exchange_rate_date,
        posted_amount_usd=amount_usd,
        lines=[
            {
                # --- الطرف المدين: النقدية / البنك بالدولار المحاسبي ---
                "account": cash_or_bank_account,
                "debit": amount_usd,
                "credit": Decimal("0.00"),
                "description": f"Receipt for payment {payment_reference}",
            },
            {
                # --- الطرف الدائن بالدولار المحاسبي ---
                "account": credit_account,
                "debit": Decimal("0.00"),
                "credit": amount_usd,
                "description": credit_description,
            },
        ],
    )

    # --- تحديث السند بشكل آمن بشرط أن يبقى غير مرحل ---
    updated_rows = payment.__class__.objects.filter(
        pk=locked_payment.pk,
        journal_entry__isnull=True,
        accounting_state=EntryState.DRAFT,
    ).update(
        journal_entry=entry,
        accounting_state=EntryState.POSTED,
    )

    if updated_rows != 1:
        raise AccountingError("Concurrent posting detected for this payment.")

    payment.journal_entry = entry
    payment.accounting_state = EntryState.POSTED

    return entry


@transaction.atomic
def post_payment_refund(*, payment_refund):
    from apps.payments.models import PaymentRefund

    # --- قفل سجل المرتجع والدفع الأصلي لمنع التكرار ---
    locked_refund = (
        PaymentRefund.objects.select_for_update()
        .select_related("payment__rental")
        .get(pk=payment_refund.pk)
    )

    if getattr(locked_refund, "journal_entry_id", None):
        raise AccountingError("This payment refund is already posted to accounting.")

    original_payment = getattr(locked_refund, "payment", None)
    if not original_payment:
        raise AccountingError("Refund must be linked to an original payment.")

    if getattr(
        original_payment, "accounting_state", "draft"
    ) != EntryState.POSTED or not getattr(original_payment, "journal_entry_id", None):
        raise AccountingError("Only posted payments can be refunded.")

    refund_amount_original = to_decimal(getattr(locked_refund, "amount", 0))
    if refund_amount_original <= 0:
        raise AccountingError("Refund amount must be greater than zero.")

    original_amount = to_decimal(getattr(original_payment, "amount_paid", 0))
    if refund_amount_original != original_amount:
        raise AccountingError("Refund amount must match the original payment amount.")

    original_currency_code = getattr(original_payment, "currency_code", "USD") or "USD"
    exchange_rate_to_usd = getattr(original_payment, "exchange_rate_to_usd", None)
    exchange_rate_date = (
        getattr(original_payment, "exchange_rate_date", None)
        or getattr(locked_refund, "refund_date", None)
        or timezone.now().date()
    )

    amount_usd = getattr(original_payment, "amount_usd", None)
    if amount_usd is not None:
        amount_usd = to_decimal(amount_usd)
    else:
        amount_usd = refund_amount_original

    if amount_usd <= 0:
        raise AccountingError("Refund posted USD amount must be greater than zero.")

    cash_or_bank_account = get_cash_or_bank_account(
        getattr(original_payment, "method", "")
    )

    rental = getattr(original_payment, "rental", None)
    if not rental:
        raise AccountingError("Original payment must be linked to a rental contract.")

    # --- إذا كان العقد مرحلًا نعيد فتح الذمة ---
    # --- وإذا كان العقد Draft نعكس عربون الإيجار ---
    if getattr(rental, "accounting_state", "draft") == EntryState.POSTED and getattr(
        rental, "journal_entry_id", None
    ):
        debit_account = get_account(AccountCodes.RENTAL_RECEIVABLES)
        debit_description = (
            f"Reopen rental receivable for refunded payment "
            f"{getattr(original_payment, 'reference', None) or original_payment.pk}"
        )
    else:
        debit_account = get_account(AccountCodes.RENTAL_ADVANCES)
        debit_description = (
            f"Reverse rental advance for refunded payment "
            f"{getattr(original_payment, 'reference', None) or original_payment.pk}"
        )

    refund_reference = (
        getattr(original_payment, "reference", None) or f"PAY-{original_payment.pk}"
    )
    entry_date = getattr(locked_refund, "refund_date", None) or timezone.now().date()

    entry = create_journal_entry(
        entry_date=entry_date,
        description=f"Refund for payment {refund_reference}",
        source_app="payments",
        source_model="PaymentRefund",
        source_id=locked_refund.pk,
        original_currency_code=original_currency_code,
        original_amount=refund_amount_original,
        exchange_rate_to_usd=exchange_rate_to_usd,
        exchange_rate_date=exchange_rate_date,
        posted_amount_usd=amount_usd,
        lines=[
            {
                # --- عكس الطرف الدائن الأصلي ---
                "account": debit_account,
                "debit": amount_usd,
                "credit": Decimal("0.00"),
                "description": debit_description,
            },
            {
                # --- خروج النقدية/البنك ---
                "account": cash_or_bank_account,
                "debit": Decimal("0.00"),
                "credit": amount_usd,
                "description": f"Cash/Bank refund for payment {refund_reference}",
            },
        ],
    )

    updated_rows = PaymentRefund.objects.filter(
        pk=locked_refund.pk,
        journal_entry__isnull=True,
    ).update(
        journal_entry=entry,
    )

    if updated_rows != 1:
        raise AccountingError("Concurrent posting detected for this payment refund.")

    payment_refund.journal_entry = entry
    return entry


def post_rental(rental_instance):
    return post_rental_revenue(rental=rental_instance)


@transaction.atomic
def post_deposit_receipt(*, rental):
    from decimal import Decimal
    from django.utils import timezone

    # --- قفل العقد من قاعدة البيانات لمنع الترحيل المكرر بالتوازي ---
    locked_rental = rental.__class__.objects.select_for_update().get(pk=rental.pk)

    # --- منع الترحيل إذا كان التأمين مرحلًا مسبقًا ---
    if getattr(locked_rental, "deposit_journal_entry_id", None):
        raise AccountingError("Deposit already posted.")

    # --- قراءة مبلغ التأمين بعد القفل ---
    amount = to_decimal(getattr(locked_rental, "deposit_amount", 0))

    # --- إذا لم يوجد مبلغ تأمين فلا نرحّل شيئًا ---
    if amount <= 0:
        return

    # --- جلب الحسابات ---
    cash_account = get_account(AccountCodes.CASH)
    deposit_account = get_account(AccountCodes.CUSTOMER_DEPOSIT)

    # --- إنشاء القيد المحاسبي ---
    entry = create_journal_entry(
        entry_date=timezone.now().date(),
        description=f"Deposit received for rental #{locked_rental.id}",
        source_app="rentals",
        source_model="RentalDeposit",
        source_id=locked_rental.id,
        lines=[
            {
                "account": cash_account,
                "debit": amount,
                "credit": Decimal("0.00"),
            },
            {
                "account": deposit_account,
                "debit": Decimal("0.00"),
                "credit": amount,
            },
        ],
    )

    # --- ربط القيد بالعقد بشكل آمن بشرط أن الحقل ما زال فارغًا ---
    updated_rows = rental.__class__.objects.filter(
        pk=locked_rental.pk,
        deposit_journal_entry__isnull=True,
    ).update(
        deposit_journal_entry=entry,
    )

    if updated_rows != 1:
        raise AccountingError("Concurrent posting detected for rental deposit.")

    # --- تحديث الكائن الحالي في الذاكرة ---
    rental.deposit_journal_entry = entry

    return entry


@transaction.atomic
def post_traffic_fine_collection(*, traffic_fine):
    # --- قفل سجل المخالفة لمنع الترحيل المكرر المتوازي ---
    locked_fine = traffic_fine.__class__.objects.select_for_update().get(
        pk=traffic_fine.pk
    )

    # --- منع تكرار قيد استلام المخالفة من الزبون ---
    if getattr(locked_fine, "customer_collection_journal_entry_id", None):
        raise AccountingError(
            "Customer collection entry already exists for this traffic fine."
        )

    # --- لا نسمح بمخالفة بدون مبلغ ---
    amount = to_decimal(getattr(locked_fine, "amount", 0))
    if amount <= 0:
        raise AccountingError("Traffic fine amount must be greater than zero.")

    # --- يجب أن تكون الحالة الحالية محصلة من الزبون ---
    if getattr(locked_fine, "status", "") != "collected":
        raise AccountingError(
            "Traffic fine status must be 'collected' before posting customer collection."
        )

    # --- تاريخ القيد من تاريخ التحصيل إن وجد ---
    entry_date = (
        getattr(locked_fine, "collected_from_customer_date", None)
        or timezone.now().date()
    )

    cash_account = get_account(AccountCodes.CASH)  # 1110
    customer_fines_receivable_account = get_account(
        AccountCodes.CUSTOMER_TRAFFIC_FINES_RECEIVABLE
    )  # 1202

    entry = create_journal_entry(
        entry_date=entry_date,
        description=f"Traffic fine collected from customer #{locked_fine.pk}",
        source_app="traffic_fines",
        source_model="TrafficFineCustomerCollection",
        source_id=locked_fine.pk,
        # =====================================================
        # أصل العملية المرجعي
        # =====================================================
        original_currency_code="USD",
        original_amount=amount,
        exchange_rate_to_usd=Decimal("1"),
        exchange_rate_date=entry_date,
        posted_amount_usd=amount,
        lines=[
            {
                # --- استلام نقدية من الزبون ---
                "account": cash_account,
                "debit": amount,
                "credit": Decimal("0.00"),
                "description": f"Cash collected for traffic fine #{locked_fine.pk}",
            },
            {
                # --- إقفال ذمة مخالفة الزبون ---
                "account": customer_fines_receivable_account,
                "debit": Decimal("0.00"),
                "credit": amount,
                "description": f"Settle customer traffic fine receivable #{locked_fine.pk}",
            },
        ],
    )

    updated_rows = traffic_fine.__class__.objects.filter(
        pk=locked_fine.pk,
        customer_collection_journal_entry__isnull=True,
    ).update(
        customer_collection_journal_entry=entry,
    )

    if updated_rows != 1:
        raise AccountingError(
            "Concurrent posting detected for traffic fine customer collection."
        )

    traffic_fine.customer_collection_journal_entry = entry
    return entry


@transaction.atomic
def post_traffic_fine_government_payment(*, traffic_fine):
    # --- قفل سجل المخالفة لمنع الترحيل المكرر المتوازي ---
    locked_fine = traffic_fine.__class__.objects.select_for_update().get(
        pk=traffic_fine.pk
    )

    # --- منع تكرار قيد دفع المخالفة للحكومة ---
    if getattr(locked_fine, "government_payment_journal_entry_id", None):
        raise AccountingError(
            "Government payment entry already exists for this traffic fine."
        )

    # --- لا نسمح بمخالفة بدون مبلغ ---
    amount = to_decimal(getattr(locked_fine, "amount", 0))
    if amount <= 0:
        raise AccountingError("Traffic fine amount must be greater than zero.")

    # --- يجب أن تكون الحالة الحالية مدفوعة للحكومة ---
    if getattr(locked_fine, "status", "") != "paid_to_government":
        raise AccountingError(
            "Traffic fine status must be 'paid_to_government' before posting government payment."
        )

    # --- تاريخ القيد من تاريخ الدفع للحكومة إن وجد ---
    entry_date = (
        getattr(locked_fine, "paid_to_government_date", None) or timezone.now().date()
    )

    government_fines_payable_account = get_account(
        AccountCodes.GOVERNMENT_TRAFFIC_FINES_PAYABLE
    )  # 2600
    cash_account = get_account(AccountCodes.CASH)  # 1110

    entry = create_journal_entry(
        entry_date=entry_date,
        description=f"Traffic fine paid to government #{locked_fine.pk}",
        source_app="traffic_fines",
        source_model="TrafficFineGovernmentPayment",
        source_id=locked_fine.pk,
        lines=[
            {
                # --- إقفال الالتزام المستحق للحكومة ---
                "account": government_fines_payable_account,
                "debit": amount,
                "credit": Decimal("0.00"),
                "description": f"Settle government traffic fine payable #{locked_fine.pk}",
            },
            {
                # --- خروج النقدية للصرف الحكومي ---
                "account": cash_account,
                "debit": Decimal("0.00"),
                "credit": amount,
                "description": f"Cash paid to government for traffic fine #{locked_fine.pk}",
            },
        ],
    )

    updated_rows = traffic_fine.__class__.objects.filter(
        pk=locked_fine.pk,
        government_payment_journal_entry__isnull=True,
    ).update(
        government_payment_journal_entry=entry,
    )

    if updated_rows != 1:
        raise AccountingError(
            "Concurrent posting detected for traffic fine government payment."
        )

    traffic_fine.government_payment_journal_entry = entry
    return entry


# ترحيل المصروف وإنشاء القيد المقابل له.
@transaction.atomic
def post_expense(*, expense: Expense):
    # --- قفل سجل المصروف من قاعدة البيانات لمنع الترحيل المكرر بالتوازي ---
    locked_expense = (
        expense.__class__.objects.select_for_update()
        .select_related("expense_account")
        .get(pk=expense.pk)
    )

    # --- منع الترحيل إذا كان هناك قيد مرتبط مسبقًا ---
    if locked_expense.journal_entry_id:
        raise AccountingError("This expense is already posted to accounting.")

    # --- منع الترحيل إذا كانت الحالة posted ---
    if locked_expense.state == EntryState.POSTED:
        raise AccountingError("This expense is already posted.")

    # --- تحويل المبلغ إلى Decimal ---
    amount = to_decimal(locked_expense.amount)

    # --- مبلغ المصروف يجب أن يكون موجبًا ---
    if amount <= 0:
        raise AccountingError("Expense amount must be greater than zero.")

    # --- التحقق من نوع حساب المصروف ---
    if locked_expense.expense_account.account_type != AccountType.EXPENSE:
        raise AccountingError("Selected expense account must be of type EXPENSE.")

    # --- تحديد حساب الصندوق أو البنك ---
    cash_or_bank_account = get_cash_or_bank_account(locked_expense.payment_method)

    # --- إنشاء القيد المحاسبي ---
    entry = create_journal_entry(
        entry_date=locked_expense.expense_date,
        description=locked_expense.description,
        source_app="accounting",
        source_model="Expense",
        source_id=locked_expense.id,
        lines=[
            {
                "account": locked_expense.expense_account,
                "debit": amount,
                "credit": Decimal("0.00"),
                "description": locked_expense.description,
            },
            {
                "account": cash_or_bank_account,
                "debit": Decimal("0.00"),
                "credit": amount,
                "description": locked_expense.description,
            },
        ],
    )

    # --- تحديث السجل بشكل آمن بشرط أن يبقى غير مرحّل ---
    updated_rows = expense.__class__.objects.filter(
        pk=locked_expense.pk,
        journal_entry__isnull=True,
        state=EntryState.DRAFT,
    ).update(
        journal_entry=entry,
        state=EntryState.POSTED,
    )

    if updated_rows != 1:
        raise AccountingError("Concurrent posting detected for this expense.")

    # --- تحديث الكائن الحالي في الذاكرة ---
    expense.journal_entry = entry
    expense.state = EntryState.POSTED

    return entry


# ترحيل الإيراد المباشر في تطبيق المحاسبة.

@transaction.atomic
def post_revenue(revenue: Revenue):
    # --- قفل سجل الإيراد من قاعدة البيانات لمنع الترحيل المكرر بالتوازي ---
    locked_revenue = (
        revenue.__class__.objects.select_for_update()
        .select_related("revenue_account")
        .get(pk=revenue.pk)
    )

    # --- منع الترحيل إذا كان هناك قيد مرتبط مسبقًا ---
    if locked_revenue.journal_entry_id:
        raise AccountingError("This revenue is already posted to accounting.")

    # --- منع الترحيل إذا كانت الحالة posted ---
    if locked_revenue.state == EntryState.POSTED:
        raise AccountingError("This revenue is already posted.")

    # --- تحويل المبلغ إلى Decimal ---
    amount = to_decimal(locked_revenue.amount)

    # --- لا يقبل مبلغًا صفريًا أو سالبًا ---
    if amount <= 0:
        raise AccountingError("Revenue amount must be greater than zero.")

    # --- التحقق من نوع حساب الإيراد ---
    if locked_revenue.revenue_account.account_type != AccountType.REVENUE:
        raise AccountingError("Selected revenue account must be of type REVENUE.")

    # --- تحديد حساب الصندوق أو البنك ---
    cash_or_bank_account = get_cash_or_bank_account(locked_revenue.payment_method)

    # --- إنشاء القيد المحاسبي ---
    entry = create_journal_entry(
        entry_date=locked_revenue.revenue_date,
        description=locked_revenue.description,
        source_app="accounting",
        source_model="Revenue",
        source_id=locked_revenue.id,
        lines=[
            {
                "account": cash_or_bank_account,
                "debit": amount,
                "credit": Decimal("0.00"),
                "description": locked_revenue.description,
            },
            {
                "account": locked_revenue.revenue_account,
                "debit": Decimal("0.00"),
                "credit": amount,
                "description": locked_revenue.description,
            },
        ],
    )

    # --- تحديث السجل بشكل آمن بشرط أن يبقى غير مرحّل ---
    updated_rows = revenue.__class__.objects.filter(
        pk=locked_revenue.pk,
        journal_entry__isnull=True,
        state=EntryState.DRAFT,
    ).update(
        journal_entry=entry,
        state=EntryState.POSTED,
    )

    if updated_rows != 1:
        raise AccountingError("Concurrent posting detected for this revenue.")

    # --- تحديث الكائن الحالي في الذاكرة ---
    revenue.journal_entry = entry
    revenue.state = EntryState.POSTED

    return entry
    # إعادة القيد الناتج.
