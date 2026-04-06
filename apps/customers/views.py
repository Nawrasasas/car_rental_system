import pandas as pd
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django import forms
from apps.vehicles.models import Vehicle
from apps.customers.models import Customer


# 1️⃣ استيراد السيارات من Excel
def import_vehicles_from_excel(request):
    if request.method == "POST" and request.FILES.get("excel_file"):
        excel_file = request.FILES["excel_file"]

        # حاشية عربية: تجاهل أول 4 صفوف واعتبار الصف الخامس هو صف أسماء الأعمدة
        df = pd.read_excel(excel_file, skiprows=4)

        # حاشية عربية: تنظيف أسماء الأعمدة من المسافات والفراغات المخفية
        df.columns = [str(col).strip() for col in df.columns]

        for _, row in df.iterrows():
            # حاشية عربية: تجاهل أي صف لا يحتوي على رقم لوحة
            plate_number = row.get("plate_number")
            if pd.isna(plate_number) or str(plate_number).strip() == "":
                continue

            Vehicle.objects.update_or_create(
                # حاشية عربية: الاعتماد على plate_number كمفتاح التحديث/الإنشاء
                plate_number=str(plate_number).strip(),
                defaults={
                    # حاشية عربية: حماية من قيم Excel الفارغة أو NaN
                    "brand": (
                        ""
                        if pd.isna(row.get("brand"))
                        else str(row.get("brand")).strip()
                    ),
                    "model": (
                        ""
                        if pd.isna(row.get("model"))
                        else str(row.get("model")).strip()
                    ),
                    "year": None if pd.isna(row.get("year")) else int(row.get("year")),
                },
            )

        # حاشية عربية: نعيد المستخدم إلى صفحة الاستيراد نفسها لأن vehicles_list غير موجود في الملف المرسل
        return redirect("vehicles:import_vehicles")

    # حاشية عربية: اسم القالب الفعلي عندك ظاهر lowercase
    return render(request, "import_vehicles.html")


# 2️⃣ Autocomplete لحقل رقم السيارة
def vehicles_autocomplete(request):
    q = request.GET.get("q", "")
    vehicles = Vehicle.objects.filter(plate_number__startswith=q)[:10]
    results = [{"number": vehicle.plate_number} for vehicle in vehicles]
    return JsonResponse(results, safe=False)


