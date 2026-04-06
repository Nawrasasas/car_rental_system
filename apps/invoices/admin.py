# PATH: apps/invoices/admin.py
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, get_object_or_404
from django.urls import path, reverse
from django import forms

from apps.attachments.inlines import AttachmentInline
from core.admin_site import custom_admin_site
from .models import Invoice, InvoiceItem, FeeType


# =========================================================
# Form مخصص: RadioSelect لـ fee_type
# =========================================================
class InvoiceAdminForm(forms.ModelForm):
    class Meta:
        model  = Invoice
        fields = "__all__"
        widgets = {
            "fee_type": forms.RadioSelect(),
        }

    def clean(self):
        cleaned = super().clean()
        is_quick_fee = cleaned.get("is_quick_fee", False)
        fee_type     = cleaned.get("fee_type", "")
        fee_type_other = cleaned.get("fee_type_other", "")

        if is_quick_fee:
            if not fee_type:
                self.add_error("fee_type", "يجب اختيار نوع الرسوم للفاتورة السريعة.")
            if fee_type == FeeType.OTHER and not fee_type_other:
                self.add_error("fee_type_other", "يرجى تحديد نوع الرسوم في حقل Other.")
        return cleaned


# =========================================================
# InvoiceItem Inline
# =========================================================
class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1

    def get_readonly_fields(self, request, obj=None):
        if obj and not obj.can_edit_core_fields():
            return ("description", "quantity", "unit_price", "tax_percent", "line_total")
        return ("line_total",)

    def has_add_permission(self, request, obj=None):
        if obj and not obj.can_edit_core_fields():
            return False
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and not obj.can_edit_core_fields():
            return False
        return super().has_delete_permission(request, obj)


# =========================================================
# InvoiceAdmin
# =========================================================
@admin.register(Invoice, site=custom_admin_site)
class InvoiceAdmin(admin.ModelAdmin):
    form = InvoiceAdminForm
    change_form_template = "admin/invoices/invoice/change_form.html"

    list_display = (
        "invoice_number", "customer", "customer_name",
        "invoice_date", "due_date", "status",
        "receivable_account", "revenue_account",
        "journal_entry", "reversed_journal_entry", "grand_total",
    )

    search_fields = (
        "invoice_number", "customer_name", "customer_email",
        "customer_phone", "customer__full_name",
    )

    list_filter = ("status", "is_quick_fee", "invoice_date", "due_date")

    ordering = ("-id",)

    inlines = [InvoiceItemInline, AttachmentInline]

    autocomplete_fields = ["customer"]

    actions = ["post_selected_invoices", "reverse_selected_invoices"]

    readonly_fields = (
        "invoice_number", "status", "subtotal", "total_tax",
        "grand_total", "journal_entry", "reversed_journal_entry",
    )

    class Media:
        css = {"all": ("css/attachment_gallery_inline.css",)}
        js  = (
            "js/attachment_gallery_inline.js",
            "admin/js/invoice_quick_fee.js",
        )

    # =========================================================
    # get_fields — ترتيب ثابت، JS يتولى الإخفاء/الإظهار
    # =========================================================
    fieldsets = (
            ("Invoice Type", {
                "fields": ("is_quick_fee", "fee_type", "fee_type_other"),
            }),
            ("Invoice Details", {
                "fields": (
                    "invoice_number", "invoice_date", "due_date", "status",
                    "from_company", "journal_entry", "reversed_journal_entry",
                ),
            }),
            ("Customer", {
                "fields": (
                    "customer", "receivable_account", "revenue_account",
                    "customer_name", "customer_email", "customer_phone", "customer_address",
                ),
            }),
            ("Notes", {
                "fields": ("notes",),
            }),
            ("Totals", {
                "fields": ("subtotal", "total_tax", "grand_total"),
            }),
        )

    # =========================================================
    # get_readonly_fields
    # =========================================================
    def get_readonly_fields(self, request, obj=None):
        base = list(self.readonly_fields)

        if obj and not obj.can_edit_core_fields():
            base.extend([
                "is_quick_fee", "fee_type", "fee_type_other",
                "invoice_date", "due_date", "from_company",
                "customer", "receivable_account", "revenue_account",
                "customer_name", "customer_email",
                "customer_phone", "customer_address",
            ])

        return tuple(base)

    # =========================================================
    # change_view — بيانات summary box
    # =========================================================
    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}

        invoice = self.get_object(request, object_id)

        if invoice:
            extra_context["show_post_button"]    = invoice.status == "draft"
            extra_context["show_reverse_button"] = invoice.status == "posted"

            # بيانات الـ summary box
            extra_context["summary"] = {
                "invoice_number": invoice.invoice_number or "—",
                "invoice_date":   invoice.invoice_date,
                "status":         invoice.status,
                "status_label":   invoice.get_status_display(),
                "is_quick_fee":   invoice.is_quick_fee,
                "fee_type_label": invoice.get_fee_type_display() if invoice.fee_type else "—",
                "customer_name":  invoice.customer_name or "—",
                "grand_total":    invoice.grand_total,
            }

        return super().change_view(request, object_id, form_url, extra_context)

    # =========================================================
    # URLs مخصصة
    # =========================================================
    def get_urls(self):
        urls = super().get_urls()
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

    def post_view(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        try:
            invoice.post()
            self.message_user(request, "تم ترحيل الفاتورة بنجاح.", level=messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"خطأ: {e}", level=messages.ERROR)
        return redirect(reverse(
            f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_change",
            args=[invoice.pk],
        ))

    def reverse_view(self, request, invoice_id):
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        try:
            invoice.reverse()
            self.message_user(request, "تم عكس الفاتورة بنجاح.", level=messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"خطأ: {e}", level=messages.ERROR)
        return redirect(reverse(
            f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_change",
            args=[invoice.pk],
        ))

    # =========================================================
    # Actions
    # =========================================================
    @admin.action(description="Post selected invoices")
    def post_selected_invoices(self, request, queryset):
        success_count  = 0
        error_messages = []
        for invoice in queryset:
            try:
                invoice.post()
                success_count += 1
            except (ValidationError, Exception) as exc:
                error_messages.append(f"{invoice.invoice_number or invoice.pk}: {exc}")

        if success_count:
            self.message_user(request, f"تم ترحيل {success_count} فاتورة بنجاح.", level=messages.SUCCESS)
        for msg in error_messages:
            self.message_user(request, msg, level=messages.ERROR)

    @admin.action(description="Reverse selected invoices")
    def reverse_selected_invoices(self, request, queryset):
        success_count  = 0
        error_messages = []
        for invoice in queryset:
            try:
                invoice.reverse()
                success_count += 1
            except (ValidationError, Exception) as exc:
                error_messages.append(f"{invoice.invoice_number or invoice.pk}: {exc}")

        if success_count:
            self.message_user(request, f"تم عكس {success_count} فاتورة بنجاح.", level=messages.SUCCESS)
        for msg in error_messages:
            self.message_user(request, msg, level=messages.ERROR)
