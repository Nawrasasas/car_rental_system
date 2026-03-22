from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect, render

from .forms import InvoiceForm
from .models import InvoiceItem


@transaction.atomic
def create_invoice(request):
    """
    إنشاء فاتورة جديدة مع عناصرها
    استخدمنا transaction.atomic حتى إذا فشل أي جزء
    لا تُحفَظ بيانات ناقصة
    """
    if request.method == 'POST':
        form = InvoiceForm(request.POST)

        if form.is_valid():
            # نحفظ الفاتورة أولاً بدون commit نهائي مؤقتًا
            invoice = form.save()

            # نقرأ القوائم القادمة من الجدول
            descriptions = request.POST.getlist('description[]')
            quantities = request.POST.getlist('quantity[]')
            unit_prices = request.POST.getlist('unit_price[]')
            taxes = request.POST.getlist('tax[]')

            created_any_item = False

            # نمشي على كل سطر من الأسطر
            for i in range(len(descriptions)):
                description = (descriptions[i] or '').strip()

                # إذا السطر فارغ نتجاهله
                if not description:
                    continue

                try:
                    quantity = Decimal(quantities[i] or '0')
                except (InvalidOperation, IndexError):
                    quantity = Decimal('0')

                try:
                    unit_price = Decimal(unit_prices[i] or '0')
                except (InvalidOperation, IndexError):
                    unit_price = Decimal('0')

                try:
                    tax_percent = Decimal(taxes[i] or '0')
                except (InvalidOperation, IndexError):
                    tax_percent = Decimal('0')

                # حماية بسيطة حتى لا تدخل قيم سالبة
                if quantity < 0:
                    quantity = Decimal('0')

                if unit_price < 0:
                    unit_price = Decimal('0')

                if tax_percent < 0:
                    tax_percent = Decimal('0')

                # إنشاء عنصر الفاتورة
                InvoiceItem.objects.create(
                    invoice=invoice,
                    description=description,
                    quantity=quantity,
                    unit_price=unit_price,
                    tax_percent=tax_percent,
                )

                created_any_item = True

            # بعد حفظ العناصر نعيد حساب المجاميع
            invoice.recalculate_totals()

            if not created_any_item:
                messages.warning(request, 'تم حفظ الفاتورة بدون عناصر.')
            else:
                messages.success(request, 'تم حفظ الفاتورة بنجاح.')

            # تستطيع لاحقًا تحويل هذا إلى صفحة التفاصيل
            return redirect('create_invoice')

    else:
        form = InvoiceForm()

    return render(request, 'invoices/invoice_form.html', {
        'form': form
    })