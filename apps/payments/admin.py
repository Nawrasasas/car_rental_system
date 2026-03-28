# PATH: apps/payments/admin.py
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.db import transaction
from core.admin_site import custom_admin_site
from .models import Payment
from apps.attachments.inlines import AttachmentInline
from .models import DepositRefund
from .services import process_deposit_refund, process_payment
from .services import process_deposit_refund
from django import forms
from django.db.models import Sum
from decimal import Decimal

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

    def get_actions(self, request):
        # --- إزالة الحذف الجماعي الافتراضي لأنه قد يتجاوز delete() في الموديل ---
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

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
        # --- نحدد هل هذه عملية إنشاء أم تعديل ---
        is_creation = not change

        try:
            # --- تمرير السند كاملًا إلى طبقة الخدمات بدل الحفظ المباشر من الأدمن ---
            process_payment(obj, is_creation=is_creation)

        except ValidationError as e:
            # --- نعيد نفس الخطأ كما هو حتى يحتفظ Django ببنية الأخطاء الصحيحة ---
            raise e


class DepositRefundAdminForm(forms.ModelForm):
    class Meta:
        model = DepositRefund
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()

        rental = cleaned_data.get("rental")
        amount = cleaned_data.get("amount")

        # --- إذا لم تكتمل البيانات الأساسية نرجع بدون فحص إضافي ---
        if not rental or amount is None:
            return cleaned_data

        # --- مجموع الاستردادات السابقة لنفس العقد مع استبعاد السجل الحالي عند التعديل ---
        total_refunded = DepositRefund.objects.filter(rental=rental).exclude(
            pk=self.instance.pk
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        deposit_amount = rental.deposit_amount or Decimal("0.00")
        new_total = total_refunded + amount

        # --- إظهار الخطأ داخل الفورم بدل صفحة Error ---
        if new_total > deposit_amount:
            self.add_error(
                "amount",
                f"Refund exceeds total deposit amount ({deposit_amount}).",
            )

        return cleaned_data


@admin.register(DepositRefund, site=custom_admin_site)
class DepositRefundAdmin(admin.ModelAdmin):
    # ... إعدادات الـ list_display وغيرها ...
    form = DepositRefundAdminForm
    def save_model(self, request, obj, form, change):
        # change == True تعني أنه يتم تعديل سجل موجود
        # change == False تعني أنه سجل جديد
        is_creation = not change

        try:
            # تمرير كائن الإرجاع إلى الخدمة لتقوم بكل العمل نيابة عن الـ Admin
            process_deposit_refund(obj, is_creation=is_creation)
        except ValidationError as e:
            # --- نعيد نفس الخطأ كما هو حتى لا نفقد بنية الرسائل المرتبطة بالحقول ---
            raise e
        
    def get_actions(self, request):
        # --- إزالة الحذف الجماعي الافتراضي لأنه قد يتجاوز delete() في الموديل ---
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions    
