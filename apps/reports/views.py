from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum
from apps.rentals.models import Rental
from .forms import SalesReportForm

@staff_member_required
def sales_report_view(request):
    form = SalesReportForm(request.GET or None)
    rentals = None
    total_sales = 0

    if form.is_valid():
        start_date = form.cleaned_data.get('start_date')
        end_date = form.cleaned_data.get('end_date')
        status = form.cleaned_data.get('status')

        # فلترة العقود بين تاريخين (بناءً على تاريخ بدء العقد)
        rentals = Rental.objects.filter(start_date__gte=start_date, start_date__lte=end_date)

        # إضافة فلتر الحالة إذا تم اختياره (Active أو Completed)
        if status:
            rentals = rentals.filter(status=status)

        # حساب إجمالي المبيعات (Net Total) للعقود المفلترة
        total_sales = rentals.aggregate(Sum('net_total'))['net_total__sum'] or 0

    context = {
        'title': 'Financial Sales Report',
        'form': form,
        'rentals': rentals,
        'total_sales': total_sales,
    }
    return render(request, 'reports/sales_report.html', context)