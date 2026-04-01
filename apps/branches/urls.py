from django.urls import path

from . import views

urlpatterns = [
    # --- API للموبايل (عام بدون تسجيل دخول) ---
    path("", views.api_branches_list, name="api_branches_list"),
    path("<int:branch_id>/", views.api_branch_detail, name="api_branch_detail"),
    # --- الصفحة القديمة HTML محفوظة على مسار مختلف ---
    path("html/", views.branch_list, name="branch_list"),
]
