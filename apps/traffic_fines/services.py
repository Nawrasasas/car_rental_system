from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import TrafficFine


class TrafficFineError(ValidationError):
    pass


@transaction.atomic
def create_traffic_fine_from_rental(*, rental):
    # --- التحقق من وجود عقد ---
    if rental is None:
        raise TrafficFineError("Rental is required.")

    # --- قراءة مبلغ المخالفة من العقد ---
    fine_amount = Decimal(str(getattr(rental, "traffic_fines", 0) or 0))

    # --- إذا لم يوجد مبلغ مخالفة فلا ننشئ سجلًا ---
    if fine_amount <= Decimal("0.00"):
        return None

    # --- منع التكرار: إذا كان هناك سجل مخالفة منشأ مسبقًا لنفس العقد ونفس السيارة ونفس المبلغ والحالة due
    # --- لا ننشئ سجلًا ثانيًا.
    existing_fine = TrafficFine.objects.filter(
        rental=rental,
        vehicle=rental.vehicle,
        amount=fine_amount,
        status=TrafficFine.STATUS_DUE,
    ).first()

    if existing_fine:
        return existing_fine

    # --- إنشاء سجل المخالفة من بيانات العقد ---
    traffic_fine = TrafficFine.objects.create(
        vehicle=rental.vehicle,
        rental=rental,
        violation_date=getattr(rental, "end_date", None)
        or getattr(rental, "start_date", None),
        violation_type="Traffic Fine From Rental Contract",
        amount=fine_amount,
        status=TrafficFine.STATUS_DUE,
        notes=f"Auto-created from rental contract {getattr(rental, 'contract_number', rental.id)}",
    )

    return traffic_fine
