from django.urls import path
from . import views

urlpatterns = [
    # صفحة العملاء
    path('', views.customer_list, name='customer_list'),
    path('add/', views.add_customer, name='add_customer'),

    # استيراد السيارات من Excel
    path('import_vehicles/', views.import_Vehicles_from_excel, name='import_vehicles'),

    # Autocomplete للسيارات
    path('vehicles_autocomplete/', views.Vehicles_autocomplete, name='vehicles_autocomplete'),
]