from django.contrib.contenttypes.models import ContentType

from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Attachment


# ---------------------------------------------------------------------------
# الأنواع المسموح بها للربط — يحمي من الوصول لأي موديل عشوائي في النظام
# ---------------------------------------------------------------------------
ALLOWED_MODEL_TYPES = {
    "vehicle_usage": ("vehicle_usage", "vehicleusage"),
    "rental": ("rentals", "rental"),
    "vehicle": ("vehicles", "vehicle"),
}


def _serialize_attachment(attachment, request=None):
    """تسلسل بيانات المرفق مع رابط مطلق للملف."""
    file_url = attachment.file_url
    # --- نبني رابطاً مطلقاً إذا كان الـ request متاحاً ---
    if file_url and request is not None:
        file_url = request.build_absolute_uri(file_url)

    return {
        "id": attachment.id,
        "filename": attachment.filename,
        "file_url": file_url or "",
        "description": attachment.description or "",
        "is_image": attachment.is_image,
        "uploaded_by": (
            {
                "id": attachment.uploaded_by.id,
                "username": attachment.uploaded_by.username,
            }
            if attachment.uploaded_by_id
            else None
        ),
        "created_at": attachment.created_at.isoformat() if attachment.created_at else None,
    }


def _resolve_content_type(model_type):
    """
    تحويل اسم النموذج النصي إلى ContentType.
    يُعيد (content_type, error_response) حيث أحدهما None.
    """
    if model_type not in ALLOWED_MODEL_TYPES:
        return None, Response(
            {
                "detail": (
                    f"model_type '{model_type}' is not supported. "
                    f"Allowed values: {list(ALLOWED_MODEL_TYPES.keys())}"
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    app_label, model_name = ALLOWED_MODEL_TYPES[model_type]
    try:
        ct = ContentType.objects.get(app_label=app_label, model=model_name)
        return ct, None
    except ContentType.DoesNotExist:
        return None, Response(
            {"detail": "Internal error: content type not found."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# ---------------------------------------------------------------------------
# نقاط نهاية API
# ---------------------------------------------------------------------------

@api_view(["POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_attachment_upload(request):
    """
    POST /attachments/upload/
    رفع ملف مرفق على أي سجل مدعوم.
    الحقول (multipart/form-data):
      - model_type: vehicle_usage | rental | vehicle
      - object_id: رقم السجل المستهدف
      - file: الملف
      - description: وصف اختياري
    """
    model_type = str(request.data.get("model_type") or "").strip().lower()
    object_id = request.data.get("object_id")
    uploaded_file = request.FILES.get("file")
    description = str(request.data.get("description") or "").strip()

    # --- التحقق من الحقول الإلزامية ---
    if not model_type:
        return Response(
            {"detail": "model_type is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if object_id is None:
        return Response(
            {"detail": "object_id is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not uploaded_file:
        return Response(
            {"detail": "file is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # --- حل نوع المحتوى ---
    content_type, err = _resolve_content_type(model_type)
    if err:
        return err

    # --- التحقق من وجود السجل المستهدف قبل الرفع ---
    model_class = content_type.model_class()
    if not model_class.objects.filter(pk=object_id).exists():
        return Response(
            {"detail": f"No {model_type} record found with id {object_id}."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # --- إنشاء المرفق مع نسب الرفع للمستخدم الحالي ---
    attachment = Attachment.objects.create(
        content_type=content_type,
        object_id=object_id,
        file=uploaded_file,
        description=description,
        uploaded_by=request.user,
    )

    return Response(
        _serialize_attachment(attachment, request),
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_attachment_list(request):
    """
    GET /attachments/?model=vehicle_usage&object_id=5
    قائمة مرفقات سجل معين.
    """
    model_type = str(request.GET.get("model") or "").strip().lower()
    object_id = request.GET.get("object_id")

    if not model_type or not object_id:
        return Response(
            {"detail": "Both 'model' and 'object_id' query parameters are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    content_type, err = _resolve_content_type(model_type)
    if err:
        return err

    attachments = (
        Attachment.objects.filter(
            content_type=content_type,
            object_id=object_id,
        )
        .select_related("uploaded_by")
        .order_by("-id")
    )

    return Response(
        {"results": [_serialize_attachment(a, request) for a in attachments]},
        status=status.HTTP_200_OK,
    )


@api_view(["DELETE"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_attachment_delete(request, attachment_id):
    """
    DELETE /attachments/{id}/
    حذف مرفق — مسموح لصاحب المرفق أو المدير/admin فقط.
    """
    attachment = Attachment.objects.filter(pk=attachment_id).first()

    if not attachment:
        return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    user = request.user
    role = getattr(user, "role", "")
    is_owner = attachment.uploaded_by_id == user.id
    is_privileged = role in ("admin", "manager")

    if not is_owner and not is_privileged:
        return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)

    # --- حذف الملف الفعلي من القرص ثم السجل من قاعدة البيانات ---
    attachment.file.delete(save=False)
    attachment.delete()

    return Response(status=status.HTTP_204_NO_CONTENT)
