from core.admin_site import custom_admin_site
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", custom_admin_site.urls),
    path("invoices/", include("apps.invoices.urls")),
    # تأكد أن المسارات تبدأ بـ apps.
    path("rentals/", include("apps.rentals.urls")),
    path("vehicles/", include("apps.vehicles.urls")),
    path("customers/", include("apps.customers.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("payments/", include("apps.payments.urls")),
    # أضف هذا السطر مع مسارات التطبيقات في config/urls.py
    path("reports/", include("apps.reports.urls")),
]
static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
