from django.http import JsonResponse
from django.shortcuts import render

from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Vehicle


def vehicle_list(request):
    # --- الشاشة القديمة HTML تبقى كما هي ---
    vehicles = Vehicle.objects.all()
    return render(request, "vehicles/list.html", {"vehicles": vehicles})


def vehicles_autocomplete(request):
    # --- autocomplete القديم محفوظ ولا يتأثر ---
    q = request.GET.get("q", "")
    vehicles = Vehicle.objects.filter(plate_number__icontains=q)[:10]
    results = [
        {"id": v.id, "text": f"{v.brand} {v.model} ({v.plate_number})"}
        for v in vehicles
    ]
    return JsonResponse({"results": results})


def _serialize_vehicle(vehicle):
    # --- تسلسل بيانات السيارة — متوافق مع Flutter الحالي ومُوسَّع بحقول الميدان ---
    brand = (vehicle.brand or "").strip()
    model = (vehicle.model or "").strip()

    return {
        # --- الحقول الأصلية (أسماؤها ثابتة لا تتغير) ---
        "id": vehicle.id,
        "plate_number": vehicle.plate_number,
        "brand": brand,
        "model": model,
        "name": f"{brand} {model}".strip(),
        "status": vehicle.status,
        "daily_price": str(vehicle.daily_price or 0),
        "branch_id": vehicle.branch_id,
        "current_odometer": vehicle.current_odometer,
        "is_active": vehicle.is_active,
        # --- حقول إضافية مهمة للعمليات الميدانية ---
        "year": vehicle.year,
        "color": vehicle.color or "",
        "fuel_type": vehicle.fuel_type or "",
        "transmission": vehicle.transmission or "",
        "seats": vehicle.seats,
        "current_fuel_level": vehicle.current_fuel_level or "",
        "key_count": vehicle.key_count,
        "insurance_expiry": (
            str(vehicle.insurance_expiry) if vehicle.insurance_expiry else None
        ),
        "registration_expiry": (
            str(vehicle.registration_expiry) if vehicle.registration_expiry else None
        ),
        "annual_inspection_date": (
            str(vehicle.annual_inspection_date)
            if vehicle.annual_inspection_date
            else None
        ),
        "notes": vehicle.notes or "",
    }


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_vehicle_list(request):
    """
    GET /vehicles/
    قائمة السيارات مع دعم الفلترة والصفحات.
    فلاتر: status, branch, page, page_size
    """
    qs = Vehicle.objects.select_related("branch").filter(is_active=True).order_by("-id")

    # --- فلترة بالحالة ---
    status_filter = request.GET.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)

    # --- فلترة بالفرع ---
    branch_filter = request.GET.get("branch")
    if branch_filter:
        qs = qs.filter(branch_id=branch_filter)

    # --- تقسيم الصفحات ---
    try:
        page = max(1, int(request.GET.get("page", 1)))
        page_size = min(50, max(1, int(request.GET.get("page_size", 20))))
    except (TypeError, ValueError):
        page, page_size = 1, 20

    total = qs.count()
    start = (page - 1) * page_size
    items = list(qs[start: start + page_size])

    return Response(
        {
            "count": total,
            "page": page,
            "page_size": page_size,
            "results": [_serialize_vehicle(v) for v in items],
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_vehicle_detail(request, vehicle_id):
    # --- تفاصيل سيارة واحدة كاملة للموبايل ---
    vehicle = Vehicle.objects.filter(pk=vehicle_id).select_related("branch").first()
    if not vehicle:
        return Response(
            {"detail": "Vehicle not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(_serialize_vehicle(vehicle), status=status.HTTP_200_OK)
