from django.urls import path
from .views import create_invoice

urlpatterns = [
    path('create/', create_invoice, name='create_invoice'),
]