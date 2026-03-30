from core.admin_site import custom_admin_site
from django.urls import path, include
from django.conf import settings
from django.views.generic import TemplateView
from django.conf.urls.static import static

urlpatterns = [
    path("", TemplateView.as_view(template_name="public/home.html"), name="home"),
    path("admin/", custom_admin_site.urls),

    # --- حاشية: هذا المسار القديم يبقى كما هو حتى لا نكسر أي شاشة HTML حالية ---
    path("accounts/", include("apps.accounts.urls")),

    # --- حاشية: هذا المسار الجديد هو الذي سيستخدمه تطبيق الموبايل ---
    path("auth/", include("apps.accounts.urls")),

    path("invoices/", include("apps.invoices.urls")),
    path("rentals/", include("apps.rentals.urls")),
    path("vehicles/", include("apps.vehicles.urls")),
    path("customers/", include("apps.customers.urls")),
    path("payments/", include("apps.payments.urls")),
    path("reports/", include("apps.reports.urls")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)