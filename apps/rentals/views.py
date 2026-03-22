import pandas as pd
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django import forms
from apps.vehicles.models import Vehicle
from apps.customers.models import Customer
from .models import Rental

# 1. عرض قائمة العقود
def rental_list(request):
    """عرض قائمة بكافة العقود المسجلة مرتبة من الأحدث."""
    rentals = Rental.objects.all().order_by('-id')
    return render(request, 'rentals/list.html', {'rentals': rentals})

# 2. دالة طباعة العقد (المتوافقة مع التعديلات الجديدة)
def print_rental_view(request, rental_id):
    """جلب بيانات العقد وإرسالها لنموذج الطباعة الاحترافي."""
    rental = get_object_or_404(Rental, id=rental_id)
    return render(request, 'rentals/print_contract.html', {'rental': rental})

# 3. استيراد بيانات السيارات من ملف Excel
def import_vehicles_from_excel(request):
    """دالة مخصصة لرفع أسطول السيارات (حوالي 200 سيارة) دفعة واحدة."""
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        try:
            df = pd.read_excel(excel_file)
            for _, row in df.iterrows():
                Vehicle.objects.update_or_create(
                    plate_number=row.get('plate_number'),
                    defaults={
                        'brand': row.get('brand', ''),
                        'model': row.get('model', ''),
                        'year': row.get('year', None),
                        'daily_rate': row.get('daily_rate', 0),
                    }
                )
            return redirect('admin:vehicles_vehicle_changelist')
        except Exception as e:
            # يمكن إضافة رسالة خطأ هنا في حال كان ملف الإكسل غير متوافق
            return render(request, 'rentals/import_vehicles.html', {'error': str(e)})
            
    return render(request, 'rentals/import_vehicles.html')

# 4. البحث التلقائي (Autocomplete) - تم التعديل ليتوافق مع JS
def vehicles_autocomplete(request):
    """توفير نتائج البحث لرقم السيارة أثناء الكتابة في نموذج العقد."""
    q = request.GET.get('q', '')
    vehicles = Vehicle.objects.filter(plate_number__icontains=q)[:10]
    # 'number' هنا تطابق li.textContent = vehicle.number الموجودة في rental_form.html
    results = [{'number': v.plate_number} for v in vehicles] 
    return JsonResponse(results, safe=False)

# 5. نموذج العقد المتطور (Rental Form)
class RentalForm(forms.ModelForm):
    plate_number = forms.CharField(
        label="Vehicle Plate Number",
        widget=forms.TextInput(attrs={
            'id': 'vehicle_number_input', 
            'autocomplete': 'off',
            'class': 'form-control',
            'placeholder': 'Start typing plate number...'
        })
    )

    class Meta:
        model = Rental
        # تأكد من إضافة الحقول الجديدة (مثل created_by أو auto_renew) إذا كنت تريد تعديلها يدوياً
        fields = ['plate_number', 'customer', 'branch', 'start_date', 'end_date']
        widgets = {
            # إظهار اختيار التاريخ والوقت (الساعة والدقيقة) بشكل احترافي
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'end_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        }

    def clean_plate_number(self):
        plate_no = self.cleaned_data['plate_number']
        try:
            vehicle = Vehicle.objects.get(plate_number=plate_no)
        except Vehicle.DoesNotExist:
            raise forms.ValidationError("السيارة غير موجودة في النظام، يرجى التأكد من رقم اللوحة.")
        return vehicle

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.vehicle = self.cleaned_data['plate_number']
        if commit:
            instance.save()
        return instance