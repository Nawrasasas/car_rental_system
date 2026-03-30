from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum
from .models import Deposit, DepositStatus, DepositRefund, DepositMethod
from apps.rentals.models import Rental
from apps.accounting.models import EntryState
from apps.accounting.services import (
    AccountingError,
    AccountCodes,
    create_journal_entry,
    get_cash_or_bank_account,
    get_account,
    to_decimal,
)


def generate_deposit_reference(*, deposit_date=None) -> str:
    # --- إذا لم يُمرر تاريخ نستخدم تاريخ اليوم ---
    deposit_date = deposit_date or timezone.now().date()

    # --- نبني البادئة الشهرية مثل: DEP-202603- ---
    prefix = f"DEP-{deposit_date.strftime('%Y%m')}-"

    # --- نجلب كل المراجع الحالية لنفس الشهر مع قفل الصفوف لمنع التكرار بالتوازي ---
    existing_refs = (
        Deposit.objects.select_for_update()
        .filter(reference__startswith=prefix)
        .values_list("reference", flat=True)
    )

    # --- نحدد أعلى تسلسل موجود ---
    max_seq = 0
    for ref in existing_refs:
        try:
            seq = int(str(ref).split("-")[-1])
            max_seq = max(max_seq, seq)
        except (ValueError, IndexError, AttributeError):
            continue

    # --- نعيد المرجع النهائي ---
    return f"{prefix}{str(max_seq + 1).zfill(4)}"


@transaction.atomic
def post_deposit_receipt(*, deposit: Deposit):
    locked_deposit = (
        Deposit.objects.select_for_update()
        .select_related("rental",)
        .get(pk=deposit.pk)
    )

    if locked_deposit.journal_entry_id:
        raise AccountingError("This deposit is already posted to accounting.")

    amount = to_decimal(locked_deposit.amount)
    if amount <= 0:
        raise AccountingError("Deposit amount must be greater than zero.")

    cash_or_bank_account = get_cash_or_bank_account(locked_deposit.method)
    customer_deposit_account = get_account(AccountCodes.CUSTOMER_DEPOSIT)

    deposit_date = locked_deposit.deposit_date or timezone.now().date()
    deposit_reference = locked_deposit.reference or f"DEP-{locked_deposit.pk}"
    contract_ref = (
        getattr(locked_deposit.rental, "contract_number", None)
        or f"Rental #{locked_deposit.rental_id}"
    )

    entry = create_journal_entry(
        entry_date=deposit_date,
        description=f"Customer deposit {deposit_reference} for contract {contract_ref}",
        source_app="deposits",
        source_model="Deposit",
        source_id=locked_deposit.id,
        lines=[
            {
                "account": cash_or_bank_account,
                "debit": amount,
                "credit": Decimal("0.00"),
                "description": f"Receipt of deposit {deposit_reference}",
            },
            {
                "account": customer_deposit_account,
                "debit": Decimal("0.00"),
                "credit": amount,
                "description": f"Customer deposit liability for contract {contract_ref}",
            },
        ],
    )

    updated_rows = Deposit.objects.filter(
        pk=locked_deposit.pk,
        journal_entry__isnull=True,
    ).update(
        journal_entry=entry,
        status=DepositStatus.RECEIVED,
    )

    if updated_rows != 1:
        raise AccountingError("Concurrent posting detected for this deposit.")

    # --- هذا الربط فقط للتوافق مع واجهة العقد الحالية ---
    # --- لكنه الآن يربط قيد مصدره Deposit فعلًا ---
    Rental.objects.filter(pk=locked_deposit.rental_id).update(
        deposit_journal_entry=entry,
    )

    deposit.journal_entry = entry
    deposit.status = DepositStatus.RECEIVED

    return entry


@transaction.atomic
def process_deposit(deposit_instance: Deposit, is_creation: bool = True):
    """
    خدمة مركزية لحفظ سند التأمين فقط.
    في هذه المرحلة لا نرحّل القيد تلقائيًا عند الحفظ.
    الترحيل يتم فقط من زر القبض المخصص.
    """
    # --- تنفيذ الفحص الكامل أولًا ---
    deposit_instance.full_clean()

    # --- توليد المرجع عند الإنشاء إذا كان فارغًا ---
    if not deposit_instance.reference:
        deposit_instance.reference = generate_deposit_reference(
            deposit_date=deposit_instance.deposit_date
        )

    # --- عند التعديل نمنع العبث بسند مرحّل ---
    if not is_creation and deposit_instance.pk:
        old_deposit = Deposit.objects.select_for_update().get(pk=deposit_instance.pk)

        if old_deposit.journal_entry_id:
            raise ValidationError("Posted deposits cannot be edited.")

    # --- حفظ السجل فقط ---
    # --- مهم: لا نرحّل القيد هنا ---
    deposit_instance.save()

    return deposit_instance


def generate_deposit_refund_reference(*, refund_date=None) -> str:
    # --- إذا لم يُمرر تاريخ نستخدم تاريخ اليوم ---
    refund_date = refund_date or timezone.now().date()

    # --- نبني البادئة الشهرية مثل: DRF-202603- ---
    prefix = f"DRF-{refund_date.strftime('%Y%m')}-"

    # --- نجلب كل المراجع الحالية لنفس الشهر مع قفل الصفوف لمنع التكرار بالتوازي ---
    existing_refs = (
        DepositRefund.objects.select_for_update()
        .filter(reference__startswith=prefix)
        .values_list("reference", flat=True)
    )

    # --- نحدد أعلى تسلسل موجود ---
    max_seq = 0
    for ref in existing_refs:
        try:
            seq = int(str(ref).split("-")[-1])
            max_seq = max(max_seq, seq)
        except (ValueError, IndexError, AttributeError):
            continue

    # --- نعيد المرجع النهائي ---
    return f"{prefix}{str(max_seq + 1).zfill(4)}"


@transaction.atomic
def post_deposit_refund(*, refund: DepositRefund):
    # --- قفل سجل الإعادة مع سند التأمين المرتبط به لمنع التوازي الخاطئ ---
    locked_refund = (
        DepositRefund.objects.select_for_update()
        .select_related("deposit", "deposit__rental",)
        .get(pk=refund.pk)
    )

    locked_deposit = Deposit.objects.select_for_update().get(
        pk=locked_refund.deposit_id
    )

    # --- منع الترحيل إذا كان السجل مرتبطًا بقيد مسبقًا ---
    if locked_refund.journal_entry_id:
        raise AccountingError("This deposit refund is already posted to accounting.")

    # --- التحقق من مبلغ الإعادة ---
    amount = to_decimal(locked_refund.amount)
    if amount <= 0:
        raise AccountingError("Refund amount must be greater than zero.")

    # --- حساب مجموع الإعادات السابقة لنفس سند التأمين مع استثناء السجل الحالي ---
    previous_refunds = (
        DepositRefund.objects.select_for_update()
        .filter(deposit=locked_deposit)
        .exclude(pk=locked_refund.pk)
        .aggregate(total=Sum("amount"))
    )["total"] or Decimal("0.00")

    # --- الرصيد المتاح قبل هذه العملية ---
    available_amount = to_decimal(locked_deposit.amount) - to_decimal(previous_refunds)

    if amount > available_amount:
        raise ValidationError(
            f"Refund amount cannot exceed remaining deposit amount ({available_amount})."
        )

    # --- تحديد حساب الصندوق أو البنك حسب طريقة الإعادة ---
    cash_or_bank_account = get_cash_or_bank_account(locked_refund.method)

    # --- حساب التزام التأمينات ---
    customer_deposit_account = get_account(AccountCodes.CUSTOMER_DEPOSIT)

    # --- بيانات وصف الحركة ---
    refund_date = locked_refund.refund_date or timezone.now().date()
    refund_reference = locked_refund.reference or f"DRF-{locked_refund.pk}"
    deposit_reference = locked_deposit.reference or f"DEP-{locked_deposit.pk}"
    contract_ref = (
        getattr(locked_deposit.rental, "contract_number", None)
        or f"Rental #{locked_deposit.rental_id}"
    )

    # --- إنشاء القيد المحاسبي العكسي:
    # --- Dr 2110 Customer Deposit
    # --- Cr Cash/Bank
    entry = create_journal_entry(
        entry_date=refund_date,
        description=f"Deposit refund {refund_reference} for deposit {deposit_reference} / contract {contract_ref}",
        source_app="deposits",
        source_model="DepositRefund",
        source_id=locked_refund.id,
        lines=[
            {
                "account": customer_deposit_account,
                "debit": amount,
                "credit": Decimal("0.00"),
                "description": f"Refund of deposit liability {deposit_reference}",
            },
            {
                "account": cash_or_bank_account,
                "debit": Decimal("0.00"),
                "credit": amount,
                "description": f"Cash/Bank payment for refund {refund_reference}",
            },
        ],
    )

    # --- ربط القيد بسجل الإعادة ---
    updated_rows = DepositRefund.objects.filter(
        pk=locked_refund.pk,
        journal_entry__isnull=True,
    ).update(journal_entry=entry)

    if updated_rows != 1:
        raise AccountingError("Concurrent posting detected for this deposit refund.")

    # --- تحديث حالة سند التأمين حسب الرصيد المتبقي ---
# --- حاشية عربية: لم نعد نعتبر الـ refund حالة مستقلة داخل Deposit.status ---
# --- الحالة الآن مشتقة فقط من وجود قيد قبض فعلي للتأمين نفسه ---
    new_status = (
        DepositStatus.RECEIVED
        if locked_deposit.journal_entry_id
        else DepositStatus.PENDING_COLLECTION
    )

    Deposit.objects.filter(pk=locked_deposit.pk).update(status=new_status)

    # --- تحديث الكائنات في الذاكرة ---
    refund.journal_entry = entry
    locked_deposit.status = new_status

    return entry


@transaction.atomic
def process_deposit_refund(refund_instance: DepositRefund, is_creation: bool = True):
    """
    خدمة مركزية لمعالجة سند إعادة التأمين.
    تقوم بـ:
    1) التحقق من الحقول
    2) قفل السجل عند التعديل
    3) منع تعديل السند المرحّل
    4) توليد المرجع عند الإنشاء
    5) الحفظ
    6) الترحيل المحاسبي
    """
    # --- تنفيذ الفحص الكامل أولًا ---
    refund_instance.full_clean()

    # --- عند الإنشاء نولد مرجعًا مستقلًا إذا كان فارغًا ---
    if not refund_instance.reference:
        refund_instance.reference = generate_deposit_refund_reference(
            refund_date=refund_instance.refund_date
        )

    # --- عند التعديل نمنع تعديل السند المرحّل ---
    if not is_creation and refund_instance.pk:
        old_refund = DepositRefund.objects.select_for_update().get(
            pk=refund_instance.pk
        )

        if old_refund.journal_entry_id:
            raise ValidationError("Posted deposit refunds cannot be edited.")

    # --- نحفظ أولًا ثم نرحّل ---
    refund_instance.save()

    if not refund_instance.journal_entry_id:
        post_deposit_refund(refund=refund_instance)

    return refund_instance


@transaction.atomic
def create_deposit_from_rental(*, rental: Rental):
    # --- قفل العقد من قاعدة البيانات لمنع التكرار المتوازي ---
    locked_rental = (
        Rental.objects.select_for_update()
        .get(pk=rental.pk)
    )

    # --- إذا لم يوجد مبلغ تأمين فلا نفعل شيئًا ---
    amount = to_decimal(getattr(locked_rental, "deposit_amount", 0))
    if amount <= 0:
        return None

    # --- نبحث أولًا هل يوجد Deposit مرتبط بهذا العقد ---
    existing_deposit = (
        Deposit.objects.select_for_update()
        .filter(rental_id=locked_rental.pk)
        .order_by("-id")
        .first()
    )

    if existing_deposit:
        update_fields = []

        if to_decimal(existing_deposit.amount) != amount:
            existing_deposit.amount = amount
            update_fields.append("amount")

        if not existing_deposit.deposit_date:
            existing_deposit.deposit_date = timezone.localdate()
            update_fields.append("deposit_date")

        if not existing_deposit.reference:
            existing_deposit.reference = generate_deposit_reference(
                deposit_date=existing_deposit.deposit_date or timezone.localdate()
            )
            update_fields.append("reference")

        # --- لا نعتبره مقبوضًا إلا إذا كان له journal_entry فعلي ---
        desired_status = (
            DepositStatus.RECEIVED
            if existing_deposit.journal_entry_id
            else DepositStatus.PENDING_COLLECTION
        )
        if existing_deposit.status != desired_status:
            existing_deposit.status = desired_status
            update_fields.append("status")

        if update_fields:
            existing_deposit.full_clean()
            existing_deposit.save(update_fields=list(dict.fromkeys(update_fields)))

        return existing_deposit

    deposit_date = timezone.localdate()

    # --- إنشاء سجل داخل التطبيق فقط بدون قبض ---
    deposit = Deposit(
        rental=locked_rental,
        amount=amount,
        deposit_date=deposit_date,
        method=DepositMethod.CASH,
        reference=generate_deposit_reference(deposit_date=deposit_date),
        status=DepositStatus.PENDING_COLLECTION,
        notes=f"Auto-created from rental contract {locked_rental.contract_number or locked_rental.pk}",
    )

    deposit.full_clean()
    deposit.save()
    return deposit
