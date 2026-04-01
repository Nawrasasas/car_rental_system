from django.contrib.auth import authenticate
from django.shortcuts import render

from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response


def home(request):
    # --- حاشية: هذه الصفحة القديمة تبقى كما هي ---
    return render(request, "accounts/home.html")


@api_view(["POST"])
@permission_classes([AllowAny])
def api_login(request):
    # --- حاشية: هذا endpoint مخصص للموبايل ---
    username = str(request.data.get("username", "")).strip()
    password = str(request.data.get("password", ""))

    if not username or not password:
        return Response(
            {"detail": "Username and password are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(request, username=username, password=password)
    if user is None:
        return Response(
            {"detail": "Invalid username or password."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- حاشية: ننشئ Token ثابت للمستخدم إن لم يكن موجودًا ---
    token, _ = Token.objects.get_or_create(user=user)

    return Response(
        {
            # --- حاشية: نعيده باسم access حتى يبقى Flutter الحالي كما هو ---
            "access": token.key,
            "user": {
                "id": user.id,
                "username": user.username,
                "role": getattr(user, "role", ""),
                "branch_id": user.branch_id,
            },
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_me(request):
    # --- حاشية: يرجع بيانات المستخدم الحالي بعد نجاح التوثيق ---
    user = request.user
    return Response(
        {
            "id": user.id,
            "username": user.username,
            "role": getattr(user, "role", ""),
            "branch_id": user.branch_id,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_dashboard_summary(request):
    """
    GET /dashboard/summary/
    ملخص إحصائي للوحة التحكم.
    النتائج مقيّدة بالفرع لأدوار delivery / manager.
    admin يرى إحصائيات كل الفروع.
    """
    # --- استيراد محلي لتجنب الاستيراد الدائري عند بدء تحميل Django ---
    from apps.vehicle_usage.models import VehicleUsage
    from apps.vehicles.models import Vehicle
    from apps.rentals.models import Rental
    from django.utils import timezone as tz

    user = request.user
    role = getattr(user, "role", "")
    now = tz.now()
    today = now.date()

    # --- تحديد فلتر الفرع حسب الدور ---
    branch_filter = {}
    usage_branch_filter = {}
    if role in ("delivery", "manager") and user.branch_id:
        branch_filter["branch_id"] = user.branch_id
        usage_branch_filter["source_branch_id"] = user.branch_id

    # --- سجلات الاستخدام الداخلي النشطة ---
    active_usages = VehicleUsage.objects.filter(
        status=VehicleUsage.STATUS_ACTIVE,
        **usage_branch_filter,
    ).count()

    # --- سجلات الاستخدام التي تجاوزت الموعد المتوقع للإرجاع ---
    overdue_usages = VehicleUsage.objects.filter(
        status=VehicleUsage.STATUS_ACTIVE,
        expected_return_datetime__lt=now,
        **usage_branch_filter,
    ).count()

    # --- السيارات المتاحة والفعّالة ---
    available_vehicles = Vehicle.objects.filter(
        status="available",
        is_active=True,
        **branch_filter,
    ).count()

    # --- عقود التأجير النشطة ---
    active_rentals = Rental.objects.filter(
        status="active",
        **branch_filter,
    ).count()

    # --- عقود التأجير النشطة التي تجاوزت تاريخ الإرجاع ---
    overdue_rentals = Rental.objects.filter(
        status="active",
        end_date__lt=today,
        **branch_filter,
    ).count()

    return Response(
        {
            "active_usages": active_usages,
            "overdue_usages": overdue_usages,
            "available_vehicles": available_vehicles,
            "active_rentals": active_rentals,
            "overdue_rentals": overdue_rentals,
        },
        status=status.HTTP_200_OK,
    )
