from django.apps import AppConfig

class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'  # هذا السطر هو الأهم ليعرف دجانجو مكان المجلد
    verbose_name = 'Administration'