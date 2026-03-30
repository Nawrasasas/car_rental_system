from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    # --- حاشية: نُبقي الصفحة القديمة حتى لا نكسر أي استعمال HTML ---
    path("", views.home, name="accounts_home"),
    # --- حاشية: API للموبايل ---
    path("login/", views.api_login, name="api_login"),
    path("me/", views.api_me, name="api_me"),
]
