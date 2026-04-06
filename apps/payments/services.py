from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Sum
from decimal import Decimal

from .models import Payment


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
    # --- الحفظ الفعلي للسند ---
    payment_instance.save()

    # --- الترحيل المحاسبي ---
    from apps.accounting.services import post_payment_receipt

    post_payment_receipt(payment=payment_instance)

    return payment_instance
