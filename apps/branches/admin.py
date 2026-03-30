from django.apps import apps
from django.contrib.admin.sites import AlreadyRegistered
from core.admin_site import custom_admin_site

# --- نأخذ كل موديلات تطبيق branches كما هي ---
app_models = apps.get_app_config("branches").get_models()

for model in app_models:
    try:
        # --- نسجل الموديلات على الأدمن المخصص الفعلي المستخدم في /admin/ ---
        custom_admin_site.register(model)
    except AlreadyRegistered:
        # --- حماية بسيطة إذا كان الموديل مسجلًا مسبقًا ---
        pass
