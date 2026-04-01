from core.admin_site import custom_admin_site
from django.urls import path, include
from django.conf import settings
from django.views.generic import TemplateView
from django.conf.urls.static import static

# --- استيراد مباشر للـ views التي تُسجَّل بدون prefix منفرد ---
from apps.accounts.views import api_dashboard_summary
from apps.branches.views import api_company_info

urlpatterns = [
    path("", TemplateView.as_view(template_name="public/home.html"), name="home"),
    path("admin/", custom_admin_site.urls),

    # --- مسار HTML القديم للويب (محفوظ لا يتغير) ---
    path("accounts/", include("apps.accounts.urls")),

    # --- مسار API للتوثيق (موبايل) ---
    path("auth/", include("apps.accounts.urls")),

    # --- لوحة التحكم: ملخص إحصائي مقيّد بالدور ---
    path("dashboard/summary/", api_dashboard_summary, name="api_dashboard_summary"),

    # --- الفروع: عامة بدون تسجيل دخول ---
    path("branches/", include("apps.branches.urls")),

    # --- معلومات الشركة: عامة بدون تسجيل دخول ---
    path("company/info/", api_company_info, name="api_company_info"),

    # --- سجلات الاستخدام الداخلي للسيارات ---
    path("vehicle-usage/", include("apps.vehicle_usage.urls")),

    # --- المرفقات والصور الميدانية ---
    path("attachments/", include("apps.attachments.urls")),

    # --- المسارات الموجودة سابقاً (لا تتغير) ---
    path("invoices/", include("apps.invoices.urls")),
    path("rentals/", include("apps.rentals.urls")),
    path("vehicles/", include("apps.vehicles.urls")),
    path("customers/", include("apps.customers.urls")),
    path("payments/", include("apps.payments.urls")),
    path("reports/", include("apps.reports.urls")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
