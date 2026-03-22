from django.contrib import admin
from .models import Customer
from core.admin_site import custom_admin_site
from apps.attachments.inlines import AttachmentInline


@admin.register(Customer, site=custom_admin_site)
class CustomerAdmin(admin.ModelAdmin):
    # عرض بيانات العميل الأساسية فقط
    list_display = ("id", "full_name", "phone", "license_number")
    search_fields = ("full_name", "phone")

    # عرض المرفقات العامة داخل نفس شاشة العميل
    inlines = [AttachmentInline]

    class Media:
        css = {"all": ("css/attachment_gallery_inline.css",)}

        js = ("js/attachment_gallery_inline.js",)
