from django.urls import path

from . import views

app_name = "attachments"

urlpatterns = [
    # --- رفع ملف مرفق على أي سجل مدعوم ---
    path("upload/", views.api_attachment_upload, name="upload"),
    # --- قائمة مرفقات سجل معين: ?model=vehicle_usage&object_id=5 ---
    path("", views.api_attachment_list, name="list"),
    # --- حذف مرفق بمعرفه ---
    path("<int:attachment_id>/", views.api_attachment_delete, name="delete"),
]
