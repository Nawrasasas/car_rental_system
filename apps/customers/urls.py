from django.urls import path
from . import views

app_name = "customers"

urlpatterns = [
    # حاشية عربية: مسارات العملاء فقط تبقى هنا
    path("", views.customer_list, name="customer_list"),
    path("add/", views.add_customer, name="add_customer"),
]
