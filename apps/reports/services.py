# مسار الملف: apps/reports/services.py

from decimal import Decimal
from django.db.models import Sum

# استيراد النماذج المحاسبية من تطبيق المحاسبة
from apps.accounting.models import Account, JournalItem, EntryState


# مسار الملف: apps/reports/services.py

from decimal import Decimal
from django.db.models import Sum
from django.urls import reverse  # مهم: لتوليد روابط الأدمن

# استيراد النماذج المحاسبية من تطبيق المحاسبة
from apps.accounting.models import Account, JournalItem


def get_general_ledger(
    account_code, start_date=None, end_date=None, vehicle_id=None, branch_id=None
):
    """
    استخراج دفتر الأستاذ (General Ledger) لحساب معين
    مع إظهار روابط القيد والمصدر الأصلي بشكل تفاعلي.
    """
    try:
        account = Account.objects.get(code=account_code)
    except Account.DoesNotExist:
        raise ValueError(f"Account with code {account_code} does not exist.")

    # نجلب أسطر اليومية المرتبطة بالحساب مع القيد المحاسبي في نفس الاستعلام
    items = JournalItem.objects.filter(
        account=account,
        journal_entry__state=EntryState.POSTED,
    ).select_related("journal_entry", "vehicle", "branch")

    if start_date:
        items = items.filter(journal_entry__entry_date__gte=start_date)
    if end_date:
        items = items.filter(journal_entry__entry_date__lte=end_date)
    if vehicle_id:
        items = items.filter(vehicle_id=vehicle_id)
    if branch_id:
        items = items.filter(branch_id=branch_id)

    # ترتيب ثابت للحركات
    items = items.order_by("journal_entry__entry_date", "journal_entry__id", "id")

    # حساب الرصيد الافتتاحي قبل تاريخ البداية
    opening_balance = Decimal("0.00")
    if start_date:
        past_items = JournalItem.objects.filter(
            account=account,
            journal_entry__state=EntryState.POSTED,
            journal_entry__entry_date__lt=start_date,
        ).aggregate(
            total_debit=Sum("debit"),
            total_credit=Sum("credit"),
        )

        t_debit = past_items["total_debit"] or Decimal("0.00")
        t_credit = past_items["total_credit"] or Decimal("0.00")

        # طبيعة الحساب:
        # 1 = Assets, 3 = Expenses => الرصيد = مدين - دائن
        # 2 = Liabilities, 4 = Revenue => الرصيد = دائن - مدين
        if str(account.code).startswith("1") or str(account.code).startswith("3"):
            opening_balance = t_debit - t_credit
        else:
            opening_balance = t_credit - t_debit

    ledger_lines = []
    running_balance = opening_balance

    # --- استيراد موديل العقود لجلب رقم العقد الحقيقي ---
    from apps.rentals.models import Rental

    # --- نجمع IDs العقود مرة واحدة لتفادي N+1 Query ---
    rental_ids = [
        item.journal_entry.source_id
        for item in items
        if item.journal_entry.source_model == "Rental" and item.journal_entry.source_id
    ]

    rentals_map = {
        rental.id: rental.contract_number
        for rental in Rental.objects.filter(id__in=rental_ids).only(
            "id", "contract_number"
        )
    }

    from apps.invoices.models import Invoice

    invoice_ids = [
        item.journal_entry.source_id
        for item in items
        if item.journal_entry.source_model == "Invoice" and item.journal_entry.source_id
    ]

    invoices_map = {
        invoice.id: invoice.invoice_number
        for invoice in Invoice.objects.filter(id__in=invoice_ids).only("id", "invoice_number")
    }

    for item in items:
        journal_entry = item.journal_entry

        # --- تحديث الرصيد التراكمي حسب طبيعة الحساب ---
        if str(account.code).startswith("1") or str(account.code).startswith("3"):
            running_balance += (item.debit or Decimal("0.00")) - (
                item.credit or Decimal("0.00")
            )
        else:
            running_balance += (item.credit or Decimal("0.00")) - (
                item.debit or Decimal("0.00")
            )

        # --- رقم القيد الصحيح من JournalEntry.entry_no ---
        # --- وإذا تعذر لسبب ما نرجع إلى fallback على ID ---
        entry_number = (
            getattr(journal_entry, "entry_no", None) or f"JE-{journal_entry.id}"
        )

        # --- رابط القيد داخل Django Admin ---
        entry_admin_url = reverse(
            "admin:accounting_journalentry_change",
            args=[journal_entry.id],
        )

        # --- مرجع المصدر النصي الافتراضي ---
        source_label = "-"
        source_admin_url = None

        if journal_entry.source_model and journal_entry.source_id:
            source_label = f"{journal_entry.source_model} #{journal_entry.source_id}"

        # --- إذا كان المصدر عقد Rental نعرض رقم العقد الحقيقي + رابطه ---
        if journal_entry.source_model == "Rental" and journal_entry.source_id:
            contract_number = rentals_map.get(journal_entry.source_id)
            if contract_number:
                source_label = contract_number

            try:
                source_admin_url = reverse(
                    "admin:rentals_rental_change",
                    args=[journal_entry.source_id],
                )
            except Exception:
                source_admin_url = None

        # --- إذا كان المصدر دفعة Payment نعرض رابط شاشة الدفعة ---
        elif journal_entry.source_model == "Payment" and journal_entry.source_id:
            source_label = f"Payment #{journal_entry.source_id}"

            try:
                source_admin_url = reverse(
                    "admin:payments_payment_change",
                    args=[journal_entry.source_id],
                )
            except Exception:
                source_admin_url = None
                # --- إذا كان المصدر فاتورة Invoice نعرض رابط شاشة الفاتورة ---
        elif journal_entry.source_model == "Invoice" and journal_entry.source_id:
            invoice_number = invoices_map.get(journal_entry.source_id)
            if invoice_number:
                source_label = invoice_number
            else:
                source_label = f"Invoice #{journal_entry.source_id}"

            try:
                source_admin_url = reverse(
                    "admin:invoices_invoice_change",
                    args=[journal_entry.source_id],
                )
            except Exception:
                source_admin_url = None

        ledger_lines.append(
            {
                "date": journal_entry.entry_date,
                "description": item.description,
                "entry_number": entry_number,  # رقم القيد لعرضه بالجدول
                "entry_admin_url": entry_admin_url,  # رابط القيد المحاسبي
                "source_label": source_label,  # رقم/مرجع المستند الأصلي
                "source_admin_url": source_admin_url,  # رابط المستند الأصلي إذا توفر
                # =====================================================
                # بيانات أصل العملية - مرجعية للعرض فقط
                # =====================================================
                # هذه الحقول مأخوذة من رأس القيد
                # وليست من سطر اليومية نفسه
                "original_currency_code": getattr(
                    journal_entry, "original_currency_code", None
                ),
                "original_amount": getattr(journal_entry, "original_amount", None),
                "exchange_rate_to_usd": getattr(
                    journal_entry, "exchange_rate_to_usd", None
                ),
                "exchange_rate_date": getattr(
                    journal_entry, "exchange_rate_date", None
                ),
                "posted_amount_usd": getattr(journal_entry, "posted_amount_usd", None),
                # =====================================================
                # القيم المحاسبية الرسمية تبقى بالدولار فقط
                # =====================================================
                "debit": item.debit or Decimal("0.00"),
                "credit": item.credit or Decimal("0.00"),
                "balance": running_balance,
            }
        )

    return {
        "account_name": account.name,
        "account_code": account.code,
        "opening_balance": opening_balance,
        "closing_balance": running_balance,
        "transactions": ledger_lines,
    }


def get_income_statement(start_date, end_date):
    """
    توليد قائمة الدخل (Income Statement) للفترة المحددة لمعرفة صافي الربح أو الخسارة.
    """
    # 1. جلب الإيرادات (Revenues) - الحسابات التي تبدأ برقم 4
    revenues = Account.objects.filter(code__startswith="4")
    revenue_data = []
    total_revenue = Decimal("0.00")

    for acc in revenues:
        items = JournalItem.objects.filter(
            account=acc,
            journal_entry__state=EntryState.POSTED,
            journal_entry__entry_date__range=(start_date, end_date),
        ).aggregate(debit=Sum("debit"), credit=Sum("credit"))
        # طبيعة الإيراد دائن، لذا الرصيد = الدائن - المدين
        balance = (items["credit"] or Decimal("0.00")) - (
            items["debit"] or Decimal("0.00")
        )

        # لا نعرض الحسابات الصفرية لتنظيف التقرير
        if balance != 0:
            revenue_data.append(
                {"code": acc.code, "name": acc.name, "balance": balance}
            )
            total_revenue += balance

    # 2. جلب المصروفات (Expenses) - الحسابات التي تبدأ برقم 3
    expenses = Account.objects.filter(code__startswith="3")
    expense_data = []
    total_expense = Decimal("0.00")

    for acc in expenses:
        items = JournalItem.objects.filter(
            account=acc,
            journal_entry__state=EntryState.POSTED,
            journal_entry__entry_date__range=(start_date, end_date),
        ).aggregate(debit=Sum("debit"), credit=Sum("credit"))
        # طبيعة المصروف مدين، لذا الرصيد = المدين - الدائن
        balance = (items["debit"] or Decimal("0.00")) - (
            items["credit"] or Decimal("0.00")
        )

        # لا نعرض الحسابات الصفرية
        if balance != 0:
            expense_data.append(
                {"code": acc.code, "name": acc.name, "balance": balance}
            )
            total_expense += balance

    # 3. حساب صافي الدخل (Net Income)
    net_income = total_revenue - total_expense

    return {
        "period_start": start_date,
        "period_end": end_date,
        "revenues": revenue_data,
        "total_revenue": total_revenue,
        "expenses": expense_data,
        "total_expense": total_expense,
        "net_income": net_income,
    }


def get_sales_report(start_date=None, end_date=None, status=None):
    from apps.rentals.models import Rental

    rentals = Rental.objects.select_related("vehicle", "customer").all()

    if start_date:
        rentals = rentals.filter(start_date__date__gte=start_date)

    if end_date:
        rentals = rentals.filter(start_date__date__lte=end_date)

    if status:
        rentals = rentals.filter(status=status)

    rentals = rentals.order_by("-start_date", "-id")

    total_sales = rentals.aggregate(total=Sum("net_total"))["total"] or Decimal("0.00")

    return {
        "rentals": rentals,
        "total_sales": total_sales,
    }
