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


def vehicles_autocomplete(request):
    # --- حاشية: نُبقي autocomplete القديم حتى لا نكسره ---
    q = request.GET.get("q", "")
    vehicles = Vehicle.objects.filter(plate_number__icontains=q)[:10]
    results = [
        {"id": v.id, "text": f"{v.brand} {v.model} ({v.plate_number})"}
        for v in vehicles
    ]
    return JsonResponse({"results": results})


def _serialize_vehicle(vehicle):
    # --- حاشية: هذا الشكل متوافق مع Flutter الحالي ---
    brand = (vehicle.brand or "").strip()
    model = (vehicle.model or "").strip()

    return {
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
    }


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_vehicle_list(request):
    # --- حاشية: نرجع كل السيارات في هذه المرحلة الأولى كما هي ---
    vehicles = Vehicle.objects.select_related("branch").all().order_by("-id")
    return Response(
        {"results": [_serialize_vehicle(vehicle) for vehicle in vehicles]},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_vehicle_detail(request, vehicle_id):
    # --- حاشية: تفاصيل سيارة واحدة للموبايل ---
    vehicle = Vehicle.objects.filter(pk=vehicle_id).select_related("branch").first()
    if not vehicle:
        return Response(
            {"detail": "Vehicle not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(_serialize_vehicle(vehicle), status=status.HTTP_200_OK)
