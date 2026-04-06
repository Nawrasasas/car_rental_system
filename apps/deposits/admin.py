# PATH: apps/deposits/admin.py
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from core.admin_site import custom_admin_site
from .models import Deposit, DepositRefund, DepositStatus
from .services import process_deposit, process_deposit_refund
from django.utils.html import format_html
from django.forms.models import BaseInlineFormSet


class DepositRefundInlineFormSet(BaseInlineFormSet):
    def clean(self):
        # --- تنفيذ فحص Django الأساسي أولًا ---
        super().clean()

        # --- إذا كان هناك أخطاء أخرى أصلًا فلا نكمل ---
        if any(self.errors):
            return

        for form in self.forms:
            # --- نتجاهل الصفوف الفارغة ---
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue

            # --- نتجاهل الصفوف المحذوفة إن وُجدت ---
            if form.cleaned_data.get("DELETE", False):
                continue

            refund = form.instance

            # --- إذا كان هذا Refund موجودًا مسبقًا ومرحّلًا وتم تعديل أي حقل فيه ---
            # --- نعرض رسالة داخل الفورم بدل صفحة خطأ ---
            if refund and refund.pk and refund.journal_entry_id and form.changed_data:
                raise ValidationError(
                    "Posted deposit refunds cannot be edited. Please add a new refund line instead."
                )


class DepositRefundInline(admin.TabularInline):
    model = DepositRefund
    formset = DepositRefundInlineFormSet
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


class DepositCollectionStatusFilter(admin.SimpleListFilter):
    # --- فلتر مشتق من وجود قيد القبض الفعلي ---
    title = "Collection Status"
    parameter_name = "collection_status"

    def lookups(self, request, model_admin):
        return (
            ("pending_collection", "Pending Collection"),
            ("received", "Received"),
        )

    def queryset(self, request, queryset):
        value = self.value()

        # --- إذا لا يوجد قيد قبض بعد فالحالة المشتقة هي Pending Collection ---
        if value == "pending_collection":
            return queryset.filter(journal_entry__isnull=True)

        # --- إذا وجد قيد قبض فالحالة المشتقة هي Received ---
        if value == "received":
            return queryset.filter(journal_entry__isnull=False)

        return queryset


class DepositHasRemainingFilter(admin.SimpleListFilter):
    title = "Remaining Balance"
    parameter_name = "has_remaining"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Has Remaining Balance"),
            ("no", "Fully Refunded"),
        )

    def queryset(self, request, queryset):
        from django.db.models import Sum, F, ExpressionWrapper, DecimalField
        from django.db.models.functions import Coalesce

        qs = queryset.annotate(
            total_refunded=Coalesce(
                Sum("refunds__amount"),
                0,
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        ).annotate(
            remaining=ExpressionWrapper(
                F("amount") - F("total_refunded"),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        )

        if self.value() == "yes":
            return qs.filter(remaining__gt=0)

        if self.value() == "no":
            return qs.filter(remaining__lte=0)

        return queryset


class DepositAdmin(admin.ModelAdmin):
    # الأعمدة الظاهرة في قائمة التأمينات
    list_display = (
        "reference",
        "rental",
        "amount",
        "deposit_date",
        "method",
        "journal_entry",
        "created_at",
        "refunded_amount_display",
        "remaining_amount_display",
        "refund_summary",
    )

    # الفلاتر الجانبية
    list_filter = (
        DepositCollectionStatusFilter,
        DepositHasRemainingFilter,
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

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "rental",
                    "amount",
                    "deposit_date",
                    "method",
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

    def collection_status_display(self, obj):
        # --- حاشية عربية: الحالة هنا مشتقة فقط من وجود قيد قبض فعلي ---
        # --- لا نعتمد على الحقل المخزن status لأنه لم يعد مصدر الحقيقة ---
        derived_status = obj.calculated_status

        color_map = {
            DepositStatus.RECEIVED: ("#16a34a", "Received"),
            DepositStatus.FULLY_REFUNDED: ("#6b7280", "Fully Refunded"),
            DepositStatus.PARTIALLY_REFUNDED: ("#3b82f6", "Partially Refunded"),
            DepositStatus.PENDING_COLLECTION: ("#f59e0b", "Pending Collection"),
        }
        color, label = color_map.get(derived_status, ("#f59e0b", "Pending Collection"))
        return format_html(
            '<span style="background:{}; color:white; padding:3px 10px; '
            'border-radius:20px; font-size:10px; font-weight:bold;">{}</span>',
            color,
            label,
        )

    collection_status_display.short_description = "Collection Status"

    def refund_summary(self, obj):
        refund_count = obj.refunds.count()
        if refund_count == 0:
            return "No refunds"
        return f"{refund_count} refund(s)"

    refund_summary.short_description = "Refund Summary"

    inlines = [DepositRefundInline]

    def has_add_permission(self, request):
        # --- منع إنشاء سند تأمين يدويًا من شاشة Deposits ---
        # --- لأن التأمين يجب أن يُنشأ فقط من داخل العقد ---
        return False

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
