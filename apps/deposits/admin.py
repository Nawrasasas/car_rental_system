# PATH: apps/deposits/admin.py
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from core.admin_site import custom_admin_site
from .models import Deposit, DepositRefund
from .services import process_deposit, process_deposit_refund
from django.utils.html import format_html

class DepositRefundInline(admin.TabularInline):
    model = DepositRefund
    extra = 0
    fields = (
        "reference",
        "refund_date",
        "amount",
        "method",
        "journal_entry",
        "notes",
    )
    readonly_fields = (
        "reference",
        "journal_entry",
    )


class DepositAdmin(admin.ModelAdmin):
    # الأعمدة الظاهرة في قائمة التأمينات
    list_display = (
        "reference",
        "rental",
        "amount",
        "deposit_date",
        "method",
        "status",
        "journal_entry",
        "created_at",
        "refunded_amount_display",
        "remaining_amount_display",
        "refund_summary",
    )

    # الفلاتر الجانبية
    list_filter = (
        "status",
        "method",
        "deposit_date",
        "created_at",

    )

    search_fields = (
        "reference",
        "rental__contract_number",
        "rental__customer__full_name",
        "rental__customer__phone",
        "notes",
    )

    # ترتيب السجلات الافتراضي
    ordering = ("-deposit_date", "-id")

    # حقول للقراءة فقط
    readonly_fields = (
        "reference",
        "journal_entry",
        "created_at",
        "updated_at",
    )

    # تنظيم شاشة الإدخال/التعديل
    fieldsets = (

        (
            "Basic Information",
            {
                "fields": (
                    "rental",
                    "amount",
                    "deposit_date",
                    "method",
                    "status",
                )
            },
        ),
        (
            "Accounting Information",
            {
                "fields": (
                    "reference",
                    "journal_entry",
                )
            },
        ),
        (
            "Additional Information",
            {
                "fields": (
                    "notes",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    # عدد السجلات في الصفحة
    list_per_page = 25

    def refunded_amount_display(self, obj):
        return obj.refunded_amount

    refunded_amount_display.short_description = "Refunded"

    def remaining_amount_display(self, obj):
        return obj.remaining_amount

    remaining_amount_display.short_description = "Remaining"

    def refund_summary(self, obj):
        refund_count = obj.refunds.count()
        if refund_count == 0:
            return "No refunds"
        return f"{refund_count} refund(s)"

    refund_summary.short_description = "Refund Summary"

    inlines = [DepositRefundInline]

    def save_model(self, request, obj, form, change):
        # --- تمرير الحفظ كاملًا عبر الخدمة حتى يتم التحقق والترحيل وتوليد المرجع ---
        try:
            # --- عند تعديل Deposit مرحّل، نسمح بمتابعة الحفظ فقط إذا لم تتغير بيانات السند نفسه
            # --- وذلك حتى يتمكن الأدمن من حفظ Refunds الموجودة في الـ inline بدون اعتبارها تعديلًا على السند الأصلي
            if change and obj.journal_entry_id and not form.changed_data:
                return

            process_deposit(obj, is_creation=not change)
        except ValidationError as e:
            # --- إظهار رسائل الفاليديشن داخل الأدمن بشكل واضح بدل 500 ---
            form.add_error(None, e)
            raise
        except Exception as e:
            # --- أي خطأ آخر نعرضه كرسالة واضحة في الأدمن ---
            self.message_user(request, str(e), level=messages.ERROR)
            raise

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)

        for obj in formset.deleted_objects:
            obj.delete()

        for obj in instances:
            if isinstance(obj, DepositRefund):
                obj.deposit = form.instance
                process_deposit_refund(obj, is_creation=not bool(obj.pk))
            else:
                obj.save()

        formset.save_m2m()

    change_form_template = "admin/deposits/deposit/change_form.html"

    class Media:
        css = {
            "all": ("admin/css/deposit_admin.css",)
        }

custom_admin_site.register(Deposit, DepositAdmin)
