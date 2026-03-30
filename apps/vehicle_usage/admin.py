from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from django.utils import timezone
from django.utils.safestring import mark_safe
from core.admin_site import custom_admin_site
from .models import VehicleUsage


class UsageStatusFilter(admin.SimpleListFilter):
    # --- فلتر حالة الاستخدام الداخلي ---
    title = "By Usage Status"
    parameter_name = "usage_status"

    def lookups(self, request, model_admin):
        return (
            ("active", "Active"),
            ("returned", "Returned"),
            ("cancelled", "Cancelled"),
            ("overdue", "Overdue"),
        )

    def queryset(self, request, queryset):
        value = self.value()

        if value == "active":
            return queryset.filter(status=VehicleUsage.STATUS_ACTIVE)

        if value == "returned":
            return queryset.filter(status=VehicleUsage.STATUS_RETURNED)

        if value == "cancelled":
            return queryset.filter(status=VehicleUsage.STATUS_CANCELLED)

        if value == "overdue":
            return queryset.filter(
                status=VehicleUsage.STATUS_ACTIVE,
                expected_return_datetime__isnull=False,
                expected_return_datetime__lt=timezone.now(),
            )

        return queryset


@admin.register(VehicleUsage, site=custom_admin_site)
class VehicleUsageAdmin(admin.ModelAdmin):
    # --- الأعمدة الظاهرة في القائمة ---
    list_display = (
        "usage_no",
        "vehicle",
        "employee_name",
        "purpose",
        "source_branch_display",
        "destination_branch_display",
        "start_time_display",
        "expected_return_display",
        "actual_return_display",
        "status_badge",
        "created_by",
    )

    # --- الفلاتر الجانبية ---
    list_filter = (
        UsageStatusFilter,
        "purpose",
        "source_branch",
        "destination_branch",
        "vehicle__brand",
        "vehicle__status",
        "created_by",
    )

    # --- البحث ---
    search_fields = (
        "usage_no",
        "vehicle__plate_number",
        "vehicle__brand",
        "vehicle__model",
        "employee_name",
        "employee_phone",
        "handover_by",
        "received_by",
        "source_branch__name",
        "destination_branch__name",
        "notes",
    )

    # --- الترتيب ---
    ordering = ("-start_datetime", "-id")

    # --- autocomplete لتسهيل اختيار السيارة ---
    autocomplete_fields = ("vehicle",)

    # --- حقول لا تُعدل يدويًا ---
    readonly_fields = (
        "usage_no",
        "source_branch",
        "created_by",
        "created_at",
        "updated_at",
        "close_usage_button",
    )

    fieldsets = (
        (
            "1) Usage / Transfer Information",
            {
                "fields": (
                    ("usage_no",),
                    ("vehicle", "status"),
                    ("purpose",),
                    ("source_branch", "destination_branch"),
                    ("employee_name", "employee_phone"),
                    ("handover_by", "received_by"),
                    ("start_datetime", "expected_return_datetime"),
                    ("pickup_odometer", "return_odometer"),
                    ("actual_return_datetime",),
                    ("notes",),
                )
            },
        ),
        (
            "2) System Tracking",
            {
                "fields": (
                    ("created_by",),
                    ("created_at", "updated_at"),
                    ("close_usage_button",),
                )
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        # --- تسجيل منشئ السجل عند أول إنشاء ---
        if not change and not obj.created_by:
            obj.created_by = request.user

        super().save_model(request, obj, form, change)

    def response_change(self, request, obj):
        # --- زر إغلاق الاستخدام / إكمال النقل من شاشة السجل ---
        if "_close_usage" in request.POST:
            try:
                obj.close_usage()

                success_message = "Vehicle usage closed successfully."
                if obj.purpose == VehicleUsage.PURPOSE_TRANSFER:
                    success_message = "Vehicle transfer completed successfully."

                self.message_user(
                    request,
                    success_message,
                    level=messages.SUCCESS,
                )
            except ValidationError as e:
                self.message_user(request, str(e), level=messages.ERROR)
            except Exception as e:
                self.message_user(request, str(e), level=messages.ERROR)

            return HttpResponseRedirect(request.path)

        return super().response_change(request, obj)

    def get_queryset(self, request):
        # --- تحسين الاستعلامات ---
        qs = super().get_queryset(request)
        return qs.select_related(
            "vehicle",
            "vehicle__branch",
            "source_branch",
            "destination_branch",
            "created_by",
        )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))

        # --- فرع الانطلاق ورقم الحركة حقول تاريخية ثابتة من لحظة الإنشاء ---
        readonly.extend(["usage_no", "source_branch"])

        if obj and obj.status in (
            VehicleUsage.STATUS_RETURNED,
            VehicleUsage.STATUS_CANCELLED,
        ):
            readonly.extend(
                [
                    "vehicle",
                    "employee_name",
                    "employee_phone",
                    "purpose",
                    "handover_by",
                    "received_by",
                    "destination_branch",
                    "notes",
                    "start_datetime",
                    "expected_return_datetime",
                    "actual_return_datetime",
                    "pickup_odometer",
                    "return_odometer",
                    "status",
                ]
            )

        return tuple(dict.fromkeys(readonly))

    def _format_local_datetime(self, value):
        # --- توحيد عرض أي datetime حسب التوقيت المحلي ---
        if not value:
            return "-"

        if timezone.is_aware(value):
            value = timezone.localtime(value)

        return value.strftime("%d-%m-%Y %H:%M")

    def start_time_display(self, obj):
        return self._format_local_datetime(obj.start_datetime)

    start_time_display.short_description = "START TIME"

    def expected_return_display(self, obj):
        return self._format_local_datetime(obj.expected_return_datetime)

    expected_return_display.short_description = "EXPECTED RETURN"

    def actual_return_display(self, obj):
        return self._format_local_datetime(obj.actual_return_datetime)

    actual_return_display.short_description = "ACTUAL RETURN"

    def source_branch_display(self, obj):
        # --- عرض فرع الانطلاق التاريخي ---
        return obj.source_branch.name if obj.source_branch else "-"

    source_branch_display.short_description = "FROM BRANCH"

    def destination_branch_display(self, obj):
        # --- عرض الفرع المقابل / الوجهة عند النقل ---
        return obj.destination_branch.name if obj.destination_branch else "-"

    destination_branch_display.short_description = "TO BRANCH"

    def status_badge(self, obj):
        colors = {
            VehicleUsage.STATUS_ACTIVE: "#ef4444",
            VehicleUsage.STATUS_RETURNED: "#16a34a",
            VehicleUsage.STATUS_CANCELLED: "#6b7280",
        }

        label = obj.get_status_display()
        color = colors.get(obj.status, "#334155")

        # --- إذا الاستخدام متأخر نضيف شارة Overdue ---
        overdue_badge = ""
        if (
            obj.status == VehicleUsage.STATUS_ACTIVE
            and obj.expected_return_datetime
            and obj.expected_return_datetime < timezone.now()
        ):
            overdue_badge = mark_safe(
                '<span style="background:#dc2626; color:white; padding:3px 10px; '
                'border-radius:20px; font-size:10px; font-weight:bold; margin-left:6px;">'
                "Overdue</span>"
            )

        return format_html(
            '<span style="background:{}; color:white; padding:3px 10px; '
            'border-radius:20px; font-size:10px; font-weight:bold;">{}</span>{}',
            color,
            label,
            overdue_badge,
        )

    status_badge.short_description = "STATUS"

    def close_usage_button(self, obj):
        # --- زر إغلاق الاستخدام / إكمال النقل من داخل السجل ---
        if not obj or not obj.pk:
            return "Save the record first to enable actions."

        if obj.status in [VehicleUsage.STATUS_RETURNED, VehicleUsage.STATUS_CANCELLED]:
            return "Close action is not available for this record."

        button_label = "Close Usage"
        if obj.purpose == VehicleUsage.PURPOSE_TRANSFER:
            button_label = "Complete Transfer"

        return mark_safe(
            '<button type="submit" name="_close_usage" value="1" '
            'style="background:#16a34a; color:white; padding:10px 16px; '
            'border:none; border-radius:6px; text-decoration:none; font-weight:bold; cursor:pointer;">'
            f"{button_label}"
            "</button>"
        )

    close_usage_button.short_description = "Close Usage"
