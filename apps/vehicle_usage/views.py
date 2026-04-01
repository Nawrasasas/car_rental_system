from django.core.exceptions import ValidationError
from django.utils import timezone

from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import VehicleUsage


# ---------------------------------------------------------------------------
# مساعدات داخلية
# ---------------------------------------------------------------------------

def _serialize_vehicle_usage(usage):
    """تسلسل بيانات سجل الاستخدام الداخلي بالكامل للموبايل."""
    vehicle = usage.vehicle

    return {
        "id": usage.id,
        "usage_no": usage.usage_no,
        "status": usage.status,
        "purpose": usage.purpose,
        # --- نص العرض العربي/الإنجليزي لنوع الاستخدام ---
        "purpose_display": usage.get_purpose_display(),
        # --- هل تجاوز السجل الوقت المتوقع للإرجاع ---
        "is_overdue": (
            usage.status == VehicleUsage.STATUS_ACTIVE
            and usage.expected_return_datetime is not None
            and usage.expected_return_datetime < timezone.now()
        ),
        "vehicle": {
            "id": vehicle.id,
            "plate_number": vehicle.plate_number,
            "brand": vehicle.brand or "",
            "model": vehicle.model or "",
            "name": f"{vehicle.brand or ''} {vehicle.model or ''}".strip(),
            "status": vehicle.status,
            "current_odometer": vehicle.current_odometer,
            "color": vehicle.color or "",
            "current_fuel_level": vehicle.current_fuel_level or "",
            "key_count": vehicle.key_count,
        },
        "source_branch": (
            {"id": usage.source_branch.id, "name": usage.source_branch.name}
            if usage.source_branch_id
            else None
        ),
        "destination_branch": (
            {"id": usage.destination_branch.id, "name": usage.destination_branch.name}
            if usage.destination_branch_id
            else None
        ),
        "employee_name": usage.employee_name,
        "employee_phone": usage.employee_phone or "",
        "handover_by": usage.handover_by or "",
        "received_by": usage.received_by or "",
        "notes": usage.notes or "",
        "start_datetime": (
            usage.start_datetime.isoformat() if usage.start_datetime else None
        ),
        "expected_return_datetime": (
            usage.expected_return_datetime.isoformat()
            if usage.expected_return_datetime
            else None
        ),
        "actual_return_datetime": (
            usage.actual_return_datetime.isoformat()
            if usage.actual_return_datetime
            else None
        ),
        "pickup_odometer": usage.pickup_odometer,
        "return_odometer": usage.return_odometer,
        "created_by": (
            {"id": usage.created_by.id, "username": usage.created_by.username}
            if usage.created_by_id
            else None
        ),
        "created_at": usage.created_at.isoformat() if usage.created_at else None,
        "updated_at": usage.updated_at.isoformat() if usage.updated_at else None,
    }


def _extract_validation_errors(exc):
    """استخراج رسائل الخطأ من ValidationError بشكل موحد وقابل للعرض في الموبايل."""
    if hasattr(exc, "message_dict") and exc.message_dict:
        # --- خطأ متعدد الحقول: نعيده كـ dict للفرونت ---
        return exc.message_dict
    if hasattr(exc, "messages") and exc.messages:
        return {"detail": " | ".join(str(m) for m in exc.messages)}
    return {"detail": str(exc)}


def _get_scoped_queryset(request):
    """
    بناء الـ queryset الأساسي مع فلترة الفرع حسب دور المستخدم:
    - delivery / manager: فرعهم فقط
    - admin: كل الفروع
    """
    qs = VehicleUsage.objects.select_related(
        "vehicle",
        "source_branch",
        "destination_branch",
        "created_by",
    )
    user = request.user
    role = getattr(user, "role", "")
    if role in ("delivery", "manager") and user.branch_id:
        qs = qs.filter(source_branch_id=user.branch_id)
    return qs


def _paginate(qs, request):
    """تقسيم الصفحات البسيط: page / page_size."""
    try:
        page = max(1, int(request.GET.get("page", 1)))
        page_size = min(50, max(1, int(request.GET.get("page_size", 20))))
    except (TypeError, ValueError):
        page, page_size = 1, 20

    total = qs.count()
    start = (page - 1) * page_size
    items = list(qs[start: start + page_size])
    return total, page, page_size, items


# ---------------------------------------------------------------------------
# نقاط نهاية API
# ---------------------------------------------------------------------------

@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_vehicle_usage_list(request):
    """
    GET /vehicle-usage/
    قائمة سجلات الاستخدام مع فلترة وصفحات.
    فلاتر مدعومة: status, purpose, branch (admin فقط)
    """
    qs = _get_scoped_queryset(request)

    # --- فلترة بالحالة ---
    status_filter = request.GET.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)

    # --- فلترة بنوع الاستخدام ---
    purpose_filter = request.GET.get("purpose")
    if purpose_filter:
        qs = qs.filter(purpose=purpose_filter)

    # --- فلترة بالفرع متاحة للمدير العام فقط ---
    branch_filter = request.GET.get("branch")
    if branch_filter and getattr(request.user, "role", "") == "admin":
        qs = qs.filter(source_branch_id=branch_filter)

    qs = qs.order_by("-start_datetime")
    total, page, page_size, items = _paginate(qs, request)

    return Response(
        {
            "count": total,
            "page": page,
            "page_size": page_size,
            "results": [_serialize_vehicle_usage(u) for u in items],
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_vehicle_usage_detail(request, usage_id):
    """GET /vehicle-usage/{id}/ — تفاصيل سجل استخدام واحد."""
    usage = (
        VehicleUsage.objects.select_related(
            "vehicle", "source_branch", "destination_branch", "created_by"
        )
        .filter(pk=usage_id)
        .first()
    )

    if not usage:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    # --- موظف التوصيل أو مدير الفرع لا يرى سجلات فرع آخر ---
    user = request.user
    role = getattr(user, "role", "")
    if (
        role in ("delivery", "manager")
        and user.branch_id
        and usage.source_branch_id != user.branch_id
    ):
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    return Response(_serialize_vehicle_usage(usage), status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_vehicle_usage_close(request, usage_id):
    """
    POST /vehicle-usage/{id}/close/
    إغلاق سجل الاستخدام عند تسليم أو إعادة السيارة.
    الحقول المطلوبة: return_odometer
    الحقول الاختيارية: received_by, notes
    """
    usage = (
        VehicleUsage.objects.select_related("vehicle", "source_branch")
        .filter(pk=usage_id)
        .first()
    )

    if not usage:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    # --- التحقق من الصلاحية: delivery / manager يغلق فرعه فقط ---
    user = request.user
    role = getattr(user, "role", "")
    if (
        role in ("delivery", "manager")
        and user.branch_id
        and usage.source_branch_id != user.branch_id
    ):
        return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

    if usage.status != VehicleUsage.STATUS_ACTIVE:
        return Response(
            {"detail": f"Cannot close a '{usage.status}' usage record."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- التحقق من عداد الإرجاع ---
    raw_odometer = request.data.get("return_odometer")
    if raw_odometer is None:
        return Response(
            {"detail": "return_odometer is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        return_odometer = int(raw_odometer)
    except (TypeError, ValueError):
        return Response(
            {"detail": "return_odometer must be a valid integer."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- تحديث الحقول الاختيارية قبل استدعاء close_usage() ---
    received_by = str(request.data.get("received_by") or "").strip()
    notes = str(request.data.get("notes") or "").strip()

    usage.return_odometer = return_odometer
    if received_by:
        usage.received_by = received_by
    if notes:
        usage.notes = notes

    try:
        # --- close_usage() يتولى الحفظ الذري وتحديث حالة السيارة ---
        usage.close_usage()
    except ValidationError as exc:
        return Response(
            _extract_validation_errors(exc),
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- إعادة تحميل كامل بعد الإغلاق لضمان دقة البيانات المُعادة ---
    usage.refresh_from_db()
    usage.vehicle.refresh_from_db()

    return Response(_serialize_vehicle_usage(usage), status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_vehicle_usage_cancel(request, usage_id):
    """
    POST /vehicle-usage/{id}/cancel/
    إلغاء سجل نشط — للمديرين والمدير العام فقط.
    """
    user = request.user
    role = getattr(user, "role", "")

    if role not in ("admin", "manager"):
        return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

    usage = (
        VehicleUsage.objects.select_related("vehicle")
        .filter(pk=usage_id)
        .first()
    )

    if not usage:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    # --- مدير الفرع يلغي فرعه فقط ---
    if role == "manager" and user.branch_id and usage.source_branch_id != user.branch_id:
        return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

    if usage.status != VehicleUsage.STATUS_ACTIVE:
        return Response(
            {"detail": f"Cannot cancel a '{usage.status}' usage record."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        usage.status = VehicleUsage.STATUS_CANCELLED
        usage.save()
    except ValidationError as exc:
        return Response(
            _extract_validation_errors(exc),
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(_serialize_vehicle_usage(usage), status=status.HTTP_200_OK)


@api_view(["PATCH"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_vehicle_usage_patch(request, usage_id):
    """
    PATCH /vehicle-usage/{id}/update/
    تحديث الملاحظات أو اسم المستلم على سجل نشط فقط.
    الحقول القابلة للتعديل: notes, received_by
    """
    usage = (
        VehicleUsage.objects.select_related("vehicle", "source_branch")
        .filter(pk=usage_id)
        .first()
    )

    if not usage:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    user = request.user
    role = getattr(user, "role", "")
    if (
        role in ("delivery", "manager")
        and user.branch_id
        and usage.source_branch_id != user.branch_id
    ):
        return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

    if usage.status != VehicleUsage.STATUS_ACTIVE:
        return Response(
            {"detail": "Only active usage records can be updated."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- نسمح فقط بتعديل الملاحظات واسم المستلم لحماية سلامة البيانات ---
    changed = False
    if "notes" in request.data:
        usage.notes = str(request.data["notes"] or "").strip()
        changed = True
    if "received_by" in request.data:
        usage.received_by = str(request.data["received_by"] or "").strip()
        changed = True

    if not changed:
        return Response(
            {"detail": "No updatable fields provided. Allowed: notes, received_by."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        usage.save()
    except ValidationError as exc:
        return Response(
            _extract_validation_errors(exc),
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(_serialize_vehicle_usage(usage), status=status.HTTP_200_OK)
