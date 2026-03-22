from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.html import format_html

from core.admin_site import custom_admin_site
from .models import Payment
from apps.attachments.inlines import AttachmentInline

@admin.register(Payment, site=custom_admin_site)
class PaymentAdmin(admin.ModelAdmin):
    # الأعمدة الظاهرة في قائمة السندات.
    list_display = (
        "reference",
        "rental",
        "amount_paid",
        "method",
        "status_tag",
        "payment_date",
        "accounting_state",
    )

    # الفلاتر الجانبية.
    list_filter = ("status", "method", "payment_date", "accounting_state")

    # حقول البحث.
    search_fields = ("reference", "rental__id", "notes")

    # مرجع السند والقيد الناتج حقول آلية للقراءة فقط.
    readonly_fields = ("reference", "journal_entry")
    
    inlines = [AttachmentInline]

    class Media:
        css = {"all": ("css/attachment_gallery_inline.css",)}

        js = ("js/attachment_gallery_inline.js",)


    def status_tag(self, obj):
        # إذا كانت الحالة مكتملة نعرض الوسم باللون الأخضر.
        if obj.status == "completed":
            color = "#28a745"
            text = "COMPLETED"
        # إذا كانت الحالة معلقة نعرض لونًا مميزًا لها.
        elif obj.status == "pending":
            color = "#dc3545"
            text = "PENDING"
        # بقية الحالات تعرض بلون رمادي.
        else:
            color = "#6c757d"
            text = obj.get_status_display().upper()

        # بناء الـ HTML النهائي مع تمرير المتغيرات بصورة آمنة.
        return format_html(
            '<span style="background-color: {}; color: white; padding: 5px 12px; '
            'border-radius: 15px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            text,
        )

    # تسمية العمود داخل القائمة.
    status_tag.short_description = "STATUS"

    def get_readonly_fields(self, request, obj=None):
        # نبدأ من الحقول الآلية الأساسية.
        base_fields = list(self.readonly_fields)

        # إذا كان السند مرحلًا نجعل بقية الحقول الحساسة للقراءة فقط.
        if obj and (obj.accounting_state == "posted" or obj.journal_entry_id):
            base_fields.extend(
                [
                    "rental",
                    "amount_paid",
                    "method",
                    "status",
                    "payment_date",
                    "notes",
                    "accounting_state",
                ]
            )

        # إعادة الحقول النهائية.
        return tuple(base_fields)

    def has_delete_permission(self, request, obj=None):
        # منع حذف السند إذا كان مرحلًا أو مرتبطًا بقيد.
        if obj and (obj.accounting_state == "posted" or obj.journal_entry_id):
            return False
        # خلاف ذلك نرجع إلى سلوك Django الافتراضي.
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        # عند تعديل سند موجود نقرأ حالته القديمة.
        if change:
            old_obj = Payment.objects.get(pk=obj.pk)
            # إذا كان السند القديم مرحلًا نمنع التعديل.
            if old_obj.accounting_state == "posted" or old_obj.journal_entry_id:
                raise ValidationError("Posted payments cannot be edited.")
        # إذا كان كل شيء صحيحًا نتابع الحفظ.
        super().save_model(request, obj, form, change)
