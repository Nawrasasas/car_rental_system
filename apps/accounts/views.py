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
