from django.urls import path

# --- حاشية: نبقي الاستيراد القديم لمسار import حتى لا نكسر الموجود ---
from apps.customers import views as customer_views
from . import views

app_name = "vehicles"

urlpatterns = [
    # --- حاشية: API للموبايل ---
    path("", views.api_vehicle_list, name="api_vehicle_list"),
    path("<int:vehicle_id>/", views.api_vehicle_detail, name="api_vehicle_detail"),
    # --- حاشية: المسارات القديمة تبقى ---
    path(
        "import-vehicles/",
        customer_views.import_vehicles_from_excel,
        name="import_vehicles",
    ),
    path(
        "vehicles-autocomplete/",
        views.vehicles_autocomplete,
        name="vehicles_autocomplete",
    ),
]
