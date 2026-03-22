from django.apps import AppConfig


class AttachmentsConfig(AppConfig):
    # --- النوع الافتراضي للمفاتيح الأساسية ---
    default_auto_field = "django.db.models.BigAutoField"

    # --- اسم التطبيق الكامل داخل المشروع ---
    name = "apps.attachments"

    # --- الاسم الظاهر داخليًا ---
    verbose_name = "Attachments"
