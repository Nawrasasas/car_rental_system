# PATH: apps/exchange_rates/admin.py
from django.contrib import admin
from django.utils.html import format_html
from core.admin_site import custom_admin_site
from .models import ExchangeRate


@admin.register(ExchangeRate, site=custom_admin_site)
class ExchangeRateAdmin(admin.ModelAdmin):

    list_display = (
        "currency_code",
        "units_per_usd",
        "rate_to_usd_display",
        "effective_date",
        "created_by",
        "notes_short",
    )

    list_filter = ("currency_code", "effective_date")

    search_fields = ("currency_code", "notes")

    ordering = ("-effective_date", "currency_code")

    readonly_fields = (
        "created_by",
        "created_at",
        "updated_at",
        "rate_to_usd_display",
    )

    fieldsets = (
        (
            "Exchange Rate",
            {
                "fields": (
                    "currency_code",
                    "units_per_usd",
                    "rate_to_usd_display",
                    "effective_date",
                    "notes",
                )
            },
        ),
        (
            "Audit",
            {
                "fields": ("created_by", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def rate_to_usd_display(self, obj=None):
        """يعرض المضاعف الداخلي المحسوب — للتأكيد فقط، لا يُعدَّل يدوياً"""
        if obj and obj.pk and obj.units_per_usd and obj.units_per_usd > 0:
            rate = obj.rate_to_usd
            return format_html(
                '<span style="color:#6b7280; font-size:12px;">'
                '1 {} = {} USD &nbsp;|&nbsp; <strong style="color:#1d4ed8;">1 USD = {} {}</strong>'
                '</span>',
                obj.currency_code,
                rate,
                obj.units_per_usd,
                obj.currency_code,
            )
        return "—"

    rate_to_usd_display.short_description = "Computed Rate"

    def notes_short(self, obj):
        if obj.notes:
            return obj.notes[:50] + ("…" if len(obj.notes) > 50 else "")
        return "—"

    notes_short.short_description = "Notes"

    def save_model(self, request, obj, form, change):
        # نحفظ الموظف الذي أدخل السعر تلقائيًا
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
