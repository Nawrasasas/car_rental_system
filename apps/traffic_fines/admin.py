# PATH: apps/traffic_fines/admin.py
from django.contrib import admin
from django.db import transaction
from core.admin_site import custom_admin_site
from apps.accounting.services import (
    post_traffic_fine_collection,
    post_traffic_fine_government_payment,
)
from .models import TrafficFine


class GovernmentDueFilter(admin.SimpleListFilter):
    # --- فلتر يميز المخالفات التي ما زالت مستحقة للحكومة ---
    title = "By Government Settlement"
    parameter_name = "government_settlement"

    def lookups(self, request, model_admin):
        return (
            ("due_to_government", "Due to Government"),
            ("paid_to_government", "Paid to Government"),
        )

    def queryset(self, request, queryset):
        value = self.value()

        if value == "due_to_government":
            # --- كل مخالفة لم تُدفع للحكومة بعد تعتبر ما زالت مستحقة ---
            return queryset.exclude(status=TrafficFine.STATUS_PAID_TO_GOVERNMENT)

        if value == "paid_to_government":
            return queryset.filter(status=TrafficFine.STATUS_PAID_TO_GOVERNMENT)

        return queryset


@admin.register(TrafficFine, site=custom_admin_site)
class TrafficFineAdmin(admin.ModelAdmin):
    # الأعمدة الظاهرة في قائمة المخالفات
    list_display = (
        "vehicle",
        "rental",
        "violation_date",
        "violation_type",
        "amount",
        "status",
        "collected_from_customer_date",
        "paid_to_government_date",
    )

    # الفلاتر الجانبية على اليمين
    list_filter = (
        "status",
        GovernmentDueFilter,
        "violation_date",
        "vehicle__branch",
        "vehicle__status",
    )

    # البحث الجزئي:
    # - برقم لوحة السيارة
    # - بنوع المخالفة
    # - برقم العقد
    search_fields = (
        "vehicle__plate_number",
        "violation_type",
        "rental__contract_number",
    )

    # ترتيب افتراضي
    ordering = ("-violation_date", "-id")

    # تسهيل اختيار السيارة والعقد في شاشة الإضافة/التعديل
    autocomplete_fields = ("vehicle", "rental")

    # حماية بسيطة من تعديل حقول التتبع يدويًا بشكل غير مقصود
    readonly_fields = (
        "customer_collection_journal_entry",
        "government_payment_journal_entry",
        "created_at",
        "updated_at",
    )

    def get_readonly_fields(self, request, obj=None):
        # --- البداية من الحقول الأساسية للقراءة فقط ---
        readonly = list(super().get_readonly_fields(request, obj))

        if obj:
            # --- بعد تحصيل المخالفة من الزبون:
            # --- نقفل أصل المخالفة، ونبقي فقط الانتقال التالي للحكومة ممكنًا ---
            if getattr(obj, "customer_collection_journal_entry_id", None):
                readonly.extend(
                    [
                        "vehicle",
                        "rental",
                        "violation_date",
                        "violation_type",
                        "amount",
                        "notes",
                        "collected_from_customer_date",
                    ]
                )

            # --- بعد دفعها للحكومة:
            # --- نقفل كل شيء بالكامل ---
            if getattr(obj, "government_payment_journal_entry_id", None):
                readonly.extend(
                    [
                        "vehicle",
                        "rental",
                        "violation_date",
                        "violation_type",
                        "amount",
                        "status",
                        "notes",
                        "collected_from_customer_date",
                        "paid_to_government_date",
                    ]
                )

        return tuple(dict.fromkeys(readonly))

    def has_delete_permission(self, request, obj=None):
        # --- بعد وجود أي قيد محاسبي مرتبط لا نسمح بالحذف ---
        if obj and (
            getattr(obj, "customer_collection_journal_entry_id", None)
            or getattr(obj, "government_payment_journal_entry_id", None)
        ):
            return False

        return super().has_delete_permission(request, obj)

    fieldsets = (
        (
            "Traffic Fine Information",
            {
                "fields": (
                    ("vehicle", "rental"),
                    ("violation_date", "violation_type"),
                    ("amount", "status"),
                    "notes",
                )
            },
        ),
        (
            "Status Tracking",
            {
                "fields": (
                    ("collected_from_customer_date", "paid_to_government_date"),
                    ("created_at", "updated_at"),
                )
            },
        ),
        (
            "Accounting",
            {
                "fields": (
                    "customer_collection_journal_entry",
                    "government_payment_journal_entry",
                )
            },
        ),
    )

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        # --- نحفظ السجل أولاً كالمعتاد ---
        super().save_model(request, obj, form, change)

        # --- إذا أصبحت المخالفة محصلة من الزبون ولم يُنشأ قيد التحصيل بعد ---
        if (
            obj.status == TrafficFine.STATUS_COLLECTED
            and not obj.customer_collection_journal_entry_id
        ):
            post_traffic_fine_collection(traffic_fine=obj)

        # --- إذا أصبحت المخالفة مدفوعة للحكومة ولم يُنشأ قيد الدفع بعد ---
        if (
            obj.status == TrafficFine.STATUS_PAID_TO_GOVERNMENT
            and not obj.government_payment_journal_entry_id
        ):
            post_traffic_fine_government_payment(traffic_fine=obj)

    def get_queryset(self, request):
        # تحسين الاستعلامات في القائمة
        qs = super().get_queryset(request)
        return qs.select_related("vehicle", "rental", "vehicle__branch")
