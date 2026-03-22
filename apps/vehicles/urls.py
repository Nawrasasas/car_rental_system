from django.urls import path
from . import views

app_name = 'vehicles'

urlpatterns = [
    #path('import-vehicles/', views.import_vehicles_from_excel, name='import_vehicles'),
    path('vehicles-autocomplete/', views.vehicles_autocomplete, name='vehicles_autocomplete'),
]