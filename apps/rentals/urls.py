from django.urls import path
from . import views

# تعريف اسم التطبيق يسهل عملية استدعاء الروابط في القوالب (Templates)
app_name = 'rentals'

urlpatterns = [
    # 1. رابط قائمة العقود (ضروري لمراجعة الحجوزات خارج لوحة الآدمن)
    path('list/', views.rental_list, name='rental_list'),
    
    # 2. رابط طباعة العقد - قمنا بتثبيت الاسم 'print_rental' ليتوافق مع زر الآدمن
    path('print/<int:rental_id>/', views.print_rental_view, name='print_rental'),
    
    # 3. رابط استيراد السيارات من ملف Excel (مهم لرفع الـ 200 سيارة)
    path('import-vehicles/', views.import_vehicles_from_excel, name='import_vehicles'),
    
    # 4. رابط البحث التلقائي - الرابط الذي يطلبه ملف rental_form.html عبر JavaScript
    path('vehicles-autocomplete/', views.vehicles_autocomplete, name='vehicles_autocomplete'),
]