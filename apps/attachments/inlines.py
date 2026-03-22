from django.contrib.contenttypes.admin import GenericStackedInline

from .models import Attachment


class AttachmentInline(GenericStackedInline):
    # --- ربط الـ inline بموديل المرفقات العام ---
    model = Attachment

    # --- قالب مخصص على شكل Gallery ---
    template = "admin/includes/attachment_gallery_inline.html"

    # --- عنصر فارغ واحد افتراضيًا ---
    extra = 1

    # --- الحقول المعروضة داخل البطاقة ---
    fields = ("file", "description")

    # --- عدم إظهار الحقول التقنية الخاصة بالربط العام ---
    ct_field = "content_type"
    ct_fk_field = "object_id"

    # --- كلاس إضافي لسهولة الاستهداف بالـ CSS ---
    classes = ("generic-attachments-inline",)
