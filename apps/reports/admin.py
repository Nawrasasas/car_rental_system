from django.contrib import admin
from django.shortcuts import redirect
from .models import SalesReport
from core.admin_site import custom_admin_site

@admin.register(SalesReport, site=custom_admin_site)
class SalesReportAdmin(admin.ModelAdmin):
    def changelist_view(self, request, extra_context=None):
        # بمجرد الضغط على الزر في القائمة، سيتم التوجيه فوراً لصفحة التقارير
        return redirect('reports:sales_report')
