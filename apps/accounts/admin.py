from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from core.admin_site import custom_admin_site

User = get_user_model()

try:
    custom_admin_site.register(User, UserAdmin)
except Exception:
    pass

try:
    custom_admin_site.register(Group, GroupAdmin)
except Exception:
    pass
