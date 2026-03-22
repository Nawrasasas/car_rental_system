from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    # جعلنا تقرير المبيعات هو الصفحة الرئيسية المباشرة للتقارير
    path('', views.sales_report_view, name='sales_report'),
]