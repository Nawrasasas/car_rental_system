from django.conf import settings
from django.shortcuts import render

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Branch


# --- الصفحة القديمة HTML تبقى كما هي ولا تتأثر ---
def branch_list(request):
    branches = Branch.objects.all()
    return render(request, "branches/list.html", {"branches": branches})


def _serialize_branch(branch):
    # --- تسلسل بيانات الفرع مع كامل معلومات التواصل للموبايل ---
    return {
        "id": branch.id,
        "name": branch.name,
        "location": branch.location,
        "phone": branch.phone or "",
        "whatsapp": branch.whatsapp or "",
        "email": branch.email or "",
        "maps_url": branch.maps_url or "",
        "opening_hours": branch.opening_hours or "",
        "is_main_branch": branch.is_main_branch,
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def api_branches_list(request):
    # --- قائمة الفروع عامة بدون تسجيل دخول / الفرع الرئيسي أولاً ---
    branches = Branch.objects.all().order_by("-is_main_branch", "name")
    return Response(
        {"results": [_serialize_branch(b) for b in branches]},
        status=status.HTTP_200_OK,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def api_branch_detail(request, branch_id):
    # --- تفاصيل فرع واحد بالكامل ---
    branch = Branch.objects.filter(pk=branch_id).first()
    if not branch:
        return Response(
            {"detail": "Branch not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(_serialize_branch(branch), status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def api_company_info(request):
    # --- معلومات الشركة العامة تُقرأ من إعدادات Django مباشرة ---
    return Response(
        {
            "name": getattr(settings, "COMPANY_NAME", ""),
            "phone": getattr(settings, "COMPANY_PHONE", ""),
            "whatsapp": getattr(settings, "COMPANY_WHATSAPP", ""),
            "email": getattr(settings, "COMPANY_EMAIL", ""),
            "description": getattr(settings, "COMPANY_DESCRIPTION", ""),
            "website": getattr(settings, "COMPANY_WEBSITE", ""),
        },
        status=status.HTTP_200_OK,
    )
