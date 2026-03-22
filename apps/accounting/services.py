from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

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
    # صندوق / نقدية.
    CASH = "1110"
    # بنك.
    BANK = "1120"
    # ذمم مدينة / العملاء.
    ACCOUNTS_RECEIVABLE = "1210"
    # إيراد الإيجار.
    RENTAL_REVENUE = "4110"
    # مصروف الصيانة.
    MAINTENANCE_EXPENSE = "5110"
    # مصروف الوقود.
    FUEL_EXPENSE = "5120"
    # مصروف الرواتب.
    SALARY_EXPENSE = "5130"
    # مصروفات أخرى.
    OTHER_EXPENSE = "5190"


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
):
    # إنشاء رأس القيد بحالة مسودة أولًا.
    entry = JournalEntry.objects.create(
        entry_no=generate_entry_no(entry_date=entry_date),
        entry_date=entry_date,
        description=description,
        source_app=source_app,
        source_model=source_model,
        source_id=source_id,
        state=EntryState.DRAFT,
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

    # التحقق النهائي من توازن القيد قبل ترحيله.
    if total_debit != total_credit:
        raise AccountingError(
            f"Unbalanced journal entry. Debit={total_debit}, Credit={total_credit}"
        )

    # ترحيل القيد بعد اكتمال عناصره وتوازنه.
    entry.post()
    # إعادة القيد الناتج لاستخدامه في ربط المصدر.
    return entry


# تحديد حساب الصندوق أو البنك حسب وسيلة الدفع.
def get_cash_or_bank_account(payment_method: str) -> Account:
    # توحيد القيمة إلى lowercase لتسهيل المطابقة.
    method = (payment_method or "").lower()

    # النقدية تذهب إلى حساب الصندوق.
    if method in [PaymentMethod.CASH, "cash"]:
        return get_account(AccountCodes.CASH)

    # التحويل والبطاقة والبنك تذهب إلى حساب البنك.
    if method in [PaymentMethod.TRANSFER, PaymentMethod.CARD, "transfer", "card", "bank"]:
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
def post_rental_revenue(*, rental):
    # منع الترحيل المكرر إذا كان العقد مرتبطًا سابقًا بقيد.
    if getattr(rental, "journal_entry_id", None):
        raise AccountingError("This rental is already posted to accounting.")

    # منع الترحيل المكرر إذا كانت حالته المحاسبية posted.
    if getattr(rental, "accounting_state", "draft") == EntryState.POSTED:
        raise AccountingError("This rental accounting state is already posted.")

    # استخراج صافي قيمة العقد.
    amount = to_decimal(getattr(rental, "net_total", 0))

    # التحقق من أن المبلغ صالح للترحيل.
    if amount <= 0:
        raise AccountingError("Rental net total must be greater than zero.")

    # حساب الذمم المدينة.
    receivable_account = get_account(AccountCodes.ACCOUNTS_RECEIVABLE)
    # حساب إيراد الإيجار.
    revenue_account = get_account(AccountCodes.RENTAL_REVENUE)

    # إنشاء القيد الناتج عن العقد.
    entry = create_journal_entry(
        entry_date=timezone.now().date(),
        description=f"Rental revenue for contract #{rental.id}",
        source_app="rentals",
        source_model="Rental",
        source_id=rental.id,
        lines=[
            {
                "account": receivable_account,
                "debit": amount,
                "credit": Decimal("0.00"),
                "description": f"Accounts receivable for rental #{rental.id}",
            },
            {
                "account": revenue_account,
                "debit": Decimal("0.00"),
                "credit": amount,
                "description": f"Rental revenue for rental #{rental.id}",
            },
        ],
    )

    # ربط القيد بالعقد.
    rental.journal_entry = entry
    # تحديث الحالة المحاسبية للعقد.
    rental.accounting_state = EntryState.POSTED
    # حفظ الحقول المعدلة فقط.
    rental.save(update_fields=["journal_entry", "accounting_state"])

    # إعادة القيد للمستخدم أو للإدارة.
    return entry


# ترحيل سند قبض عميل لتسوية الذمم المدينة.
@transaction.atomic
def post_payment_receipt(*, payment):
    # منع إنشاء قيد جديد إذا كان السند مرتبطًا أصلًا بقيد سابق.
    if getattr(payment, "journal_entry_id", None):
        raise AccountingError("This payment is already posted to accounting.")

    # منع الترحيل المكرر عبر حالة السند المحاسبية.
    if getattr(payment, "accounting_state", "draft") == EntryState.POSTED:
        raise AccountingError("This payment accounting state is already posted.")

    # لا يسمح بترحيل دفعة غير مكتملة.
    payment_status = getattr(payment, "status", "")
    if payment_status != "completed":
        raise AccountingError("Only completed payments can be posted.")

    # مبلغ الدفعة المقبوضة.
    amount = to_decimal(getattr(payment, "amount_paid", 0))

    # المبلغ يجب أن يكون أكبر من صفر.
    if amount <= 0:
        raise AccountingError("Payment amount must be greater than zero.")

    # حساب الصندوق أو البنك وفق طريقة الدفع.
    cash_or_bank_account = get_cash_or_bank_account(getattr(payment, "method", ""))
    # حساب الذمم المدينة.
    receivable_account = get_account(AccountCodes.ACCOUNTS_RECEIVABLE)

    # رقم العقد المرتبط بالسند إن وجد.
    rental_id = getattr(payment, "rental_id", None)
    # تاريخ السند أو تاريخ اليوم إذا لم يمرر.
    payment_date = getattr(payment, "payment_date", None) or timezone.now().date()
    # المرجع النصي للسند إن وجد حتى يظهر في وصف القيد.
    payment_reference = getattr(payment, "reference", None) or f"PAY-{payment.id}"

    # إنشاء القيد المحاسبي الناتج عن القبض.
    entry = create_journal_entry(
        entry_date=payment_date,
        description=f"Customer payment {payment_reference} for rental #{rental_id}",
        source_app="payments",
        source_model="Payment",
        source_id=payment.id,
        lines=[
            {
                "account": cash_or_bank_account,
                "debit": amount,
                "credit": Decimal("0.00"),
                "description": f"Receipt for payment {payment_reference}",
            },
            {
                "account": receivable_account,
                "debit": Decimal("0.00"),
                "credit": amount,
                "description": f"Settlement of receivable for rental #{rental_id}",
            },
        ],
    )

    # ربط القيد بسند القبض.
    payment.journal_entry = entry
    # تحويل الحالة المحاسبية إلى posted.
    payment.accounting_state = EntryState.POSTED
    # حفظ التعديلات الأساسية فقط.
    payment.save(update_fields=["journal_entry", "accounting_state"])

    # إعادة القيد الناتج.
    return entry


# ترحيل المصروف وإنشاء القيد المقابل له.
@transaction.atomic
def post_expense(*, expense: Expense):
    # منع تكرار الترحيل إذا كان مرتبطًا بقيد سابق.
    if expense.journal_entry_id:
        raise AccountingError("This expense is already posted to accounting.")

    # منع تكرار الترحيل عبر الحالة.
    if expense.state == EntryState.POSTED:
        raise AccountingError("This expense is already posted.")

    # تحويل المبلغ إلى Decimal.
    amount = to_decimal(expense.amount)

    # مبلغ المصروف يجب أن يكون موجبًا.
    if amount <= 0:
        raise AccountingError("Expense amount must be greater than zero.")

    # حساب المصروف المختار يجب أن يكون من نوع EXPENSE.
    if expense.expense_account.account_type != AccountType.EXPENSE:
        raise AccountingError("Selected expense account must be of type EXPENSE.")

    # تحديد حساب الصندوق أو البنك حسب وسيلة الدفع.
    cash_or_bank_account = get_cash_or_bank_account(expense.payment_method)

    # إنشاء قيد المصروف.
    entry = create_journal_entry(
        entry_date=expense.expense_date,
        description=expense.description,
        source_app="accounting",
        source_model="Expense",
        source_id=expense.id,
        lines=[
            {
                "account": expense.expense_account,
                "debit": amount,
                "credit": Decimal("0.00"),
                "description": expense.description,
            },
            {
                "account": cash_or_bank_account,
                "debit": Decimal("0.00"),
                "credit": amount,
                "description": expense.description,
            },
        ],
    )

    # ربط القيد بالمصروف.
    expense.journal_entry = entry
    # تحديث حالة المصروف إلى posted.
    expense.state = EntryState.POSTED
    # حفظ الحقول المتغيرة فقط.
    expense.save(update_fields=["journal_entry", "state"])

    # إعادة القيد الناتج.
    return entry


# ترحيل الإيراد المباشر في تطبيق المحاسبة.
@transaction.atomic
def post_revenue(revenue: Revenue):
    # منع الترحيل إذا كان هناك قيد سابق مرتبط بالإيراد.
    if revenue.journal_entry_id:
        raise AccountingError("This revenue is already posted to accounting.")

    # منع الترحيل إذا كانت الحالة posted أصلًا.
    if revenue.state == EntryState.POSTED:
        raise AccountingError("This revenue is already posted.")

    # تحويل المبلغ إلى Decimal.
    amount = to_decimal(revenue.amount)

    # لا يقبل مبلغًا صفريًا أو سالبًا.
    if amount <= 0:
        raise AccountingError("Revenue amount must be greater than zero.")

    # حساب الإيراد المختار يجب أن يكون من نوع REVENUE.
    if revenue.revenue_account.account_type != AccountType.REVENUE:
        raise AccountingError("Selected revenue account must be of type REVENUE.")

    # تحديد حساب الصندوق أو البنك وفق وسيلة الدفع.
    cash_or_bank_account = get_cash_or_bank_account(revenue.payment_method)

    # إنشاء القيد الناتج عن الإيراد.
    entry = create_journal_entry(
        entry_date=revenue.revenue_date,
        description=revenue.description,
        source_app="accounting",
        source_model="Revenue",
        source_id=revenue.id,
        lines=[
            {
                "account": cash_or_bank_account,
                "debit": amount,
                "credit": Decimal("0.00"),
                "description": revenue.description,
            },
            {
                "account": revenue.revenue_account,
                "debit": Decimal("0.00"),
                "credit": amount,
                "description": revenue.description,
            },
        ],
    )

    # ربط القيد بالإيراد.
    revenue.journal_entry = entry
    # تحويل الحالة إلى posted.
    revenue.state = EntryState.POSTED
    # حفظ الحقول المتغيرة مع updated_at.
    revenue.save(update_fields=["journal_entry", "state", "updated_at"])

    # إعادة القيد الناتج.
    return entry
