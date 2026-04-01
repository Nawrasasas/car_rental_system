from django.urls import path

from . import views

app_name = "vehicle_usage"

urlpatterns = [
    # --- قائمة سجلات الاستخدام مع فلترة وصفحات ---
    path("", views.api_vehicle_usage_list, name="list"),
    # --- تفاصيل سجل واحد ---
    path("<int:usage_id>/", views.api_vehicle_usage_detail, name="detail"),
    # --- إغلاق السجل عند إرجاع السيارة ---
    path("<int:usage_id>/close/", views.api_vehicle_usage_close, name="close"),
    # --- إلغاء السجل (مديرون فقط) ---
    path("<int:usage_id>/cancel/", views.api_vehicle_usage_cancel, name="cancel"),
    # --- تحديث الملاحظات / اسم المستلم ---
    path("<int:usage_id>/update/", views.api_vehicle_usage_patch, name="patch"),
]
