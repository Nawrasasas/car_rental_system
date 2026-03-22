from django.apps import AppConfig

class RentalsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.rentals'  # هذا السطر هو الأهم، يخبر دجانجو بمكان التطبيق الجديد