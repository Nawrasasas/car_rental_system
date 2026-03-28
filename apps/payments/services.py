from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Sum
from decimal import Decimal
# --- استيراد موديل الدفعات لأننا سنضيف له خدمة مركزية مثل DepositRefund ---
from .models import DepositRefund, Payment

# --- استيراد خدمة الترحيل المحاسبي الخاصة بسندات القبض ---
from apps.accounting.services import post_payment_receipt


@transaction.atomic
def process_deposit_refund(refund_instance: DepositRefund, is_creation: bool = True):
    """
    خدمة مركزية لمعالجة إرجاع التأمين.
    تقوم بالتحقق، قفل السجلات، الحفظ، ومنع تجاوز مبلغ التأمين.
    """
    # --- التحقق المبدئي من صحة الحقول ---
    refund_instance.full_clean()

    # --- قفل العقد لمنع السباقات على مبلغ التأمين ---
    locked_rental = (
        type(refund_instance.rental)
        .objects.select_for_update()
        .get(pk=refund_instance.rental_id)
    )

    old_amount = Decimal("0.00")

    # --- في حالة التعديل: نقرأ السجل القديم أولًا ونمنع تعديل السجل المرحّل قبل أي حفظ ---
    if not is_creation and refund_instance.pk:
        old_refund = DepositRefund.objects.select_for_update().get(pk=refund_instance.pk)

        # --- لا نسمح بتعديل Refund مرحّل ---
        if old_refund.journal_entry_id:
            raise ValidationError("Posted deposit refunds cannot be edited.")

        old_amount = old_refund.amount or Decimal("0.00")

    # --- مجموع كل الاستردادات الحالية لنفس العقد ---
    total_refunded = (
        DepositRefund.objects.filter(rental_id=refund_instance.rental_id)
        .aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    # --- عند التعديل نطرح القيمة القديمة ثم نضيف الجديدة ---
    new_total = total_refunded - old_amount + (refund_instance.amount or Decimal("0.00"))

    # --- منع تجاوز مبلغ التأمين الأصلي للعقد ---
    deposit_amount = locked_rental.deposit_amount or Decimal("0.00")
    if new_total > deposit_amount:
        raise ValidationError(
            {"amount": f"Refund exceeds total deposit amount ({deposit_amount})."}
        )

    # --- بعد نجاح كل الفحوصات نحفظ السجل ---
    refund_instance.save()

    return refund_instance


@transaction.atomic
def process_payment(payment_instance: Payment, is_creation: bool = True):
    """
    خدمة مركزية لمعالجة سند القبض.
    تقوم بالتحقق، قفل العقد، منع تجاوز صافي العقد، الحفظ، ثم الترحيل المحاسبي.
    تُستدعى من PaymentAdmin ومن RentalAdmin ومن الـ Mobile API.
    """

    # --- بما أن الـ inline والدفعة الأولية لا يرسلان status حاليًا
    # --- نضع قيمة افتراضية آمنة حتى لا ينكسر الحفظ ---
    if not payment_instance.status:
        payment_instance.status = "completed"

    # --- التحقق الأولي من الحقول ---
    payment_instance.full_clean()

    # --- قفل العقد الحالي لمنع السباقات على مجموع الدفعات ---
    locked_rental = (
        type(payment_instance.rental)
        .objects.select_for_update()
        .get(pk=payment_instance.rental_id)
    )

    # --- إذا كانت العملية تعديلًا على دفعة موجودة
    # --- نقرأ النسخة القديمة ونمنع تعديل الدفعات المرحلة ---
    if not is_creation and payment_instance.pk:
        old_payment = Payment.objects.select_for_update().get(pk=payment_instance.pk)

        # --- لا نسمح بتعديل سند مرحل سواء من الأدمن أو من الـ API ---
        if old_payment.accounting_state == "posted" or old_payment.journal_entry_id:
            raise ValidationError("Posted payments cannot be edited.")

    # --- نحسب مجموع الدفعات لنفس العقد مع استبعاد السجل الحالي عند التعديل ---
    total_paid = Payment.objects.filter(rental_id=payment_instance.rental_id).exclude(
        pk=payment_instance.pk
    ).aggregate(total=Sum("amount_paid"))["total"] or Decimal("0.00")

    # --- المجموع الجديد بعد إضافة/تعديل هذه الدفعة ---
    new_total = total_paid + (payment_instance.amount_paid or Decimal("0.00"))

    # --- منع تجاوز صافي قيمة العقد ---
    if new_total > (locked_rental.net_total or Decimal("0.00")):
        raise ValidationError(
            {
                "amount_paid": (
                    f"Total payments cannot exceed rental net total "
                    f"({locked_rental.net_total})."
                )
            }
        )

    # --- الحفظ الفعلي للسند ---
    payment_instance.save()

    # --- الترحيل المحاسبي يتم مرة واحدة فقط
    # --- وإذا كانت الحالة مكتملة ولم يكن هناك قيد مرتبط بعد ---
    if payment_instance.status == "completed" and not payment_instance.journal_entry_id:
        post_payment_receipt(payment=payment_instance)

        # --- نعيد تحميل الكائن حتى تظهر حالة القيد والـ journal_entry المحدثة ---
        payment_instance.refresh_from_db()

    return payment_instance
