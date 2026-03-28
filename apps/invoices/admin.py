# PATH: apps/invoices/admin.py
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, get_object_or_404
from django.urls import path, reverse
# استخدام قالب مخصص فقط لصفحة تعديل الفاتورة داخل الـ admin.
from apps.attachments.inlines import AttachmentInline

from core.admin_site import custom_admin_site
from .models import Invoice, InvoiceItem


# هذا الـ inline يجعل بنود الفاتورة تظهر داخل شاشة الفاتورة نفسها.
class InvoiceItemInline(admin.TabularInline):
    # ربط الـ inline بموديل البنود.
    model = InvoiceItem

    # إظهار سطر إضافي واحد افتراضيًا.
    extra = 1

    # عند خروج الفاتورة من draft نجعل كل حقول البند للقراءة فقط.
    def get_readonly_fields(self, request, obj=None):
        if obj and not obj.can_edit_core_fields():
            return (
                "description",
                "quantity",
                "unit_price",
                "tax_percent",
                "line_total",
            )
        return ("line_total",)

    # منع إضافة بنود جديدة بعد الترحيل أو العكس.
    def has_add_permission(self, request, obj=None):
        if obj and not obj.can_edit_core_fields():
            return False
        return super().has_add_permission(request, obj)

    # منع حذف البنود بعد الترحيل أو العكس.
    def has_delete_permission(self, request, obj=None):
        if obj and not obj.can_edit_core_fields():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Invoice, site=custom_admin_site)
class InvoiceAdmin(admin.ModelAdmin):
    change_form_template = "admin/invoices/invoice/change_form.html"
    # هذه الأعمدة تظهر في قائمة الفواتير.
    list_display = (
        "invoice_number",
        "customer",
        "customer_name",
        "invoice_date",
        "due_date",
        "status",
        "receivable_account",
        "revenue_account",
        "journal_entry",
        "reversed_journal_entry",
        "grand_total",
    )

    # حقول البحث.
    search_fields = (
        "invoice_number",
        "customer_name",
        "customer_email",
        "customer_phone",
        "customer__full_name",
    )

    # الفلاتر الجانبية.
    list_filter = (
        "status",
        "invoice_date",
        "due_date",
    )

    # ترتيب افتراضي.
    ordering = ("-id",)

    # نعرض عناصر الفاتورة داخلها.
    inlines = [InvoiceItemInline, AttachmentInline]

    # ربط الأكشنات الخاصة بالترحيل والعكس من قائمة الإدارة.
    actions = ["post_selected_invoices", "reverse_selected_invoices"]

    # هذه الحقول آلية أو محسوبة لذلك تكون للقراءة فقط دائمًا.
    readonly_fields = (
        "invoice_number",
        "status",
        "subtotal",
        "total_tax",
        "grand_total",
        "journal_entry",
        "reversed_journal_entry",
       
    )

    class Media:
        css = {"all": ("css/attachment_gallery_inline.css",)}

        js = ("js/attachment_gallery_inline.js",)

    # تمرير متغيرات إضافية إلى صفحة التعديل حتى نتحكم في ظهور الأزرار.

    def change_view(self, request, object_id, form_url="", extra_context=None):
        # إنشاء قاموس إضافي إذا لم يكن موجودًا
        extra_context = extra_context or {}

        # جلب الفاتورة الحالية
        invoice = self.get_object(request, object_id)

        # نظهر زر Post فقط إذا كانت Draft
        extra_context["show_post_button"] = bool(invoice and invoice.status == "draft")

        # نظهر زر Reverse فقط إذا كانت Posted
        extra_context["show_reverse_button"] = bool(invoice and invoice.status == "posted")

        # استدعاء السلوك الأصلي لصفحة التعديل
        return super().change_view(
            request,
            object_id,
            form_url,
            extra_context=extra_context,
        )

    # ضبط ترتيب الحقول داخل نموذج الإدارة.
    def get_fields(self, request, obj=None):
        base_fields = [
            "invoice_number",
            "invoice_date",
            "due_date",
            "status",
            "from_company",
            "customer",
            "receivable_account",
            "revenue_account",
            "journal_entry",
            "reversed_journal_entry",
            "customer_name",
            "customer_email",
            "customer_phone",
            "customer_address",
            "notes",
            "subtotal",
            "total_tax",
            "grand_total",
        ]

        # نضيف الأزرار فقط بعد حفظ الفاتورة.

        return tuple(base_fields)

    # جعل الحقول الأساسية غير قابلة للتعديل بعد الترحيل أو العكس.
    def get_readonly_fields(self, request, obj=None):
        base_fields = list(self.readonly_fields)

        # إذا كانت الفاتورة ليست draft، نقفل الحقول الأساسية أيضًا.
        if obj and not obj.can_edit_core_fields():
            base_fields.extend(
                [
                    "invoice_date",
                    "due_date",
                    "from_company",
                    "customer",
                    "receivable_account",
                    "revenue_account",
                    "customer_name",
                    "customer_email",
                    "customer_phone",
                    "customer_address",
                    "notes",
                ]
            )

        return tuple(base_fields)

    # أكشن لترحيل الفواتير المحددة من قائمة الـ admin.
    @admin.action(description="Post selected invoices")
    def post_selected_invoices(self, request, queryset):
        success_count = 0
        error_messages = []

        # المرور على كل فاتورة محددة ومحاولة ترحيلها بشكل مستقل.
        for invoice in queryset:
            try:
                invoice.post()
                success_count += 1
            except ValidationError as exc:
                error_messages.append(f"{invoice.invoice_number or invoice.pk}: {exc}")
            except Exception as exc:
                error_messages.append(f"{invoice.invoice_number or invoice.pk}: {exc}")

        # عرض عدد الفواتير التي نجحت.
        if success_count:
            self.message_user(
                request,
                f"تم ترحيل {success_count} فاتورة بنجاح.",
                level=messages.SUCCESS,
            )

        # عرض الأخطاء إن وجدت بدون إيقاف بقية الفواتير.
        for error_message in error_messages:
            self.message_user(request, error_message, level=messages.ERROR)

    # أكشن لعكس الفواتير المحددة من قائمة الـ admin.
    @admin.action(description="Reverse selected invoices")
    def reverse_selected_invoices(self, request, queryset):
        success_count = 0
        error_messages = []

        # المرور على كل فاتورة محددة ومحاولة عكسها بشكل مستقل.
        for invoice in queryset:
            try:
                invoice.reverse()
                success_count += 1
            except ValidationError as exc:
                error_messages.append(f"{invoice.invoice_number or invoice.pk}: {exc}")
            except Exception as exc:
                error_messages.append(f"{invoice.invoice_number or invoice.pk}: {exc}")

        # عرض عدد الفواتير التي انعكست بنجاح.
        if success_count:
            self.message_user(
                request,
                f"تم عكس {success_count} فاتورة بنجاح.",
                level=messages.SUCCESS,
            )

        # عرض الأخطاء إن وجدت بدون إيقاف بقية الفواتير.
        for error_message in error_messages:
            self.message_user(request, error_message, level=messages.ERROR)

    # إضافة URLs مخصصة لزر Post و Reverse داخل الـ admin.
    def get_urls(self):
        urls = super().get_urls()

        # تحديد اسم التطبيق واسم الموديل ديناميكيًا
        app_label = self.model._meta.app_label
        model_name = self.model._meta.model_name

        custom_urls = [
            path(
                "<int:invoice_id>/post/",
                self.admin_site.admin_view(self.post_view),
                name="invoice_post",
            ),
            path(
                "<int:invoice_id>/reverse/",
                self.admin_site.admin_view(self.reverse_view),
                name="invoice_reverse",
            ),
        ]

        return custom_urls + urls

    # تنفيذ عملية Post من داخل الفاتورة.
    def post_view(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)

        try:
            invoice.post()
            self.message_user(
                request, "تم ترحيل الفاتورة بنجاح.", level=messages.SUCCESS
            )
        except Exception as e:
            self.message_user(request, f"خطأ: {str(e)}", level=messages.ERROR)

        return redirect(
            reverse(
                f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_change",
                args=[invoice.pk],
            )
        )

    # تنفيذ عملية Reverse من داخل الفاتورة.

    def reverse_view(self, request, invoice_id):
        # جلب الفاتورة أو إرجاع 404 إذا لم تكن موجودة
        invoice = get_object_or_404(Invoice, pk=invoice_id)

        try:
            # تنفيذ عملية العكس من الموديل نفسه
            invoice.reverse()

            # رسالة نجاح
            self.message_user(
                request,
                "تم عكس الفاتورة بنجاح.",
                level=messages.SUCCESS,
            )
        except Exception as e:
            # إظهار الخطأ للمستخدم داخل admin
            self.message_user(
                request,
                f"خطأ: {str(e)}",
                level=messages.ERROR,
            )

        # الرجوع إلى صفحة تعديل نفس الفاتورة
        return redirect(
        reverse(
            f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_change",
            args=[invoice.pk],
        )
    )
