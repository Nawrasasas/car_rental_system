from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Attachment(models.Model):
    # --- ربط عام مع أي موديل داخل المشروع ---
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name="Content Type",
    )

    # --- رقم السجل المرتبط داخل ذلك الموديل ---
    object_id = models.PositiveBigIntegerField(
        verbose_name="Object ID",
    )

    # --- الكائن المرتبط فعليًا: عقد / سيارة / زبون / فاتورة / دفعة / قيد ---
    content_object = GenericForeignKey(
        "content_type",
        "object_id",
    )

    # --- الملف المرفوع ---
    file = models.FileField(
        upload_to="attachments/%Y/%m/",
        verbose_name="File",
    )

    # --- وصف اختياري للمرفق ---
    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Description",
    )

    # --- المستخدم الذي رفع المرفق إن توفر ---
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_attachments",
        verbose_name="Uploaded By",
    )

    # --- تاريخ الإنشاء ---
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At",
    )

    # --- تاريخ آخر تعديل ---
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Updated At",
    )

    class Meta:
        # --- ترتيب الأحدث أولًا ---
        ordering = ["-id"]

        # --- أسماء العرض داخل Django ---
        verbose_name = "Attachment"
        verbose_name_plural = "Attachments"

    @property
    def filename(self):
        # --- إرجاع اسم الملف فقط بدون المسار ---
        if not self.file:
            return ""
        return self.file.name.split("/")[-1]

    @property
    def file_url(self):
        # --- إرجاع رابط الملف إن وجد ---
        if not self.file:
            return ""
        try:
            return self.file.url
        except Exception:
            return ""

    @property
    def is_image(self):
        # --- التحقق هل الملف صورة ---
        if not self.file:
            return False

        image_extensions = (
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
            ".bmp",
            ".svg",
        )

        return self.file.name.lower().endswith(image_extensions)

    def __str__(self):
        # --- تمثيل نصي واضح للمرفق ---
        return self.filename or f"Attachment #{self.pk}"
