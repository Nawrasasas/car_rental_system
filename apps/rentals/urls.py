from django.urls import path
from . import views

app_name = "rentals"

urlpatterns = [
    # --- حاشية: API للموبايل ---
    path("", views.api_rentals_list_create, name="api_rentals_list_create"),
    path("<int:rental_id>/", views.api_rental_detail, name="api_rental_detail"),
    # --- حاشية: المسارات القديمة تبقى كما هي ---

    path("print/<int:rental_id>/", views.print_rental_view, name="print_rental"),
    path(
        "vehicles-autocomplete/",
        views.vehicles_autocomplete,
        name="vehicles_autocomplete",
    ),
    # --- endpoint داخلي للأدمن: يُرجع currency_code للعقد ---
    path(
        "api/rental-currency/<int:rental_id>/",
        views.rental_currency_api,
        name="rental_currency_api",
    ),
]
