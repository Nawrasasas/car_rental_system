import pandas as pd
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django import forms
from apps.vehicles.models import Vehicle 
from apps.customers.models import Customer  # تم حذف Contract من هنا

# 1️⃣ استيراد السيارات من Excel
def import_Vehicles_from_excel(request):
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        df = pd.read_excel(excel_file)
        for _, row in df.iterrows():
            Vehicle.objects.update_or_create(
                plate_number=row['plate_number'],  # تأكد أن الاسم يطابق الموديل (غالباً plate_number)
                defaults={
                    'model': row.get('model', ''),
                    'brand': row.get('brand', ''),
                    'year': row.get('year', None),
                }
            )
        return redirect('vehicles_list')
    return render(request, 'import_Vehicles.html')

# 2️⃣ Autocomplete لحقل رقم السيارة
def Vehicles_autocomplete(request):
    q = request.GET.get('q', '')
    vehicles = Vehicle.objects.filter(plate_number__startswith=q)[:10]
    results = [{'number': vehicle.plate_number} for vehicle in vehicles]
    return JsonResponse(results, safe=False)

# 3️⃣ نموذج إضافة عميل جديد (تم تحديث الحقول لتشمل الباسبور)
class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        # أضفنا passport_number و nationality و address هنا
        fields = ['full_name', 'phone', 'email', 'license_number', 'passport_number', 'nationality', 'address']

# 4️⃣ قائمة العملاء
def customer_list(request):
    customers = Customer.objects.all()
    return render(request, 'customers_list.html', {'customers': customers})

# 5️⃣ دالة إضافة عميل
def add_customer(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('customer_list')
    else:
        form = CustomerForm()
    return render(request, 'add_customer.html', {'form': form})