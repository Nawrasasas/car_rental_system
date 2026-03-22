from django.shortcuts import render
from .models import Vehicle

def vehicle_list(request):
    vehicles = Vehicle.objects.all()
    return render(request, 'vehicles/list.html', {'vehicles': vehicles})
from django.http import JsonResponse
from .models import Vehicle

def vehicles_autocomplete(request):
    """دالة مؤقتة لإصلاح الخطأ وتشغيل السيرفر"""
    q = request.GET.get('q', '')
    vehicles = Vehicle.objects.filter(plate_number__icontains=q)[:10]
    results = [
        {'id': v.id, 'text': f"{v.brand} {v.model} ({v.plate_number})"} 
        for v in vehicles
    ]
    return JsonResponse({'results': results})