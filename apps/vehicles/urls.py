from django.urls import path

# حاشية عربية: الدوال الفعلية الحالية موجودة داخل customers.views
from apps.customers import views as customer_views

app_name = "vehicles"

urlpatterns = [
    # حاشية عربية: تفعيل مسار استيراد السيارات
    path(
        "import-vehicles/",
        customer_views.import_vehicles_from_excel,
        name="import_vehicles",
    ),
    # حاشية عربية: ربط autocomplete بالدالة الفعلية الصحيحة
    path(
        "vehicles-autocomplete/",
        customer_views.vehicles_autocomplete,
        name="vehicles_autocomplete",
    ),
]
