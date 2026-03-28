# apps/accounting/reports.py

from decimal import Decimal
from django.db.models import Sum
from .models import Account, JournalItem


def get_general_ledger(account_code, start_date=None, end_date=None):
    """
    استخراج دفتر الأستاذ لحساب معين مع الرصيد التراكمي.
    """
    account = Account.objects.get(code=account_code)

    # بناء الاستعلام الأساسي للحركات المرحلة فقط (إذا كان لديك حقل state في JournalEntry)
    # نفترض هنا أننا نجلب كل الأسطر المرتبطة بهذا الحساب
    items = JournalItem.objects.filter(account=account).select_related("journal_entry")

    if start_date:
        items = items.filter(journal_entry__entry_date__gte=start_date)
    if end_date:
        items = items.filter(journal_entry__entry_date__lte=end_date)

    items = items.order_by("journal_entry__entry_date", "id")

    # حساب الرصيد الافتتاحي (إذا كان هناك تاريخ بداية)
    opening_balance = Decimal("0.00")
    if start_date:
        past_items = JournalItem.objects.filter(
            account=account, journal_entry__entry_date__lt=start_date
        ).aggregate(total_debit=Sum("debit"), total_credit=Sum("credit"))
        t_debit = past_items["total_debit"] or Decimal("0.00")
        t_credit = past_items["total_credit"] or Decimal("0.00")

        # تحديد طبيعة الحساب (مدين أم دائن) لحساب الرصيد بشكل صحيح
        # حسابات الأصول (1) والمصروفات (3) طبيعتها مدينة
        if str(account.code).startswith("1") or str(account.code).startswith("3"):
            opening_balance = t_debit - t_credit
        else:
            opening_balance = t_credit - t_debit

    # تجهيز التقرير مع الرصيد التراكمي
    ledger_lines = []
    running_balance = opening_balance

    for item in items:
        # تحديث الرصيد بناءً على طبيعة الحساب
        if str(account.code).startswith("1") or str(account.code).startswith("3"):
            running_balance += item.debit - item.credit
        else:
            running_balance += item.credit - item.debit

        ledger_lines.append(
            {
                "date": item.journal_entry.entry_date,
                "description": item.description,
                "reference": f"{item.journal_entry.source_model} #{item.journal_entry.source_id}",
                "debit": item.debit,
                "credit": item.credit,
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

# apps/accounting/reports.py


def get_income_statement(start_date, end_date):
    """
    توليد قائمة الدخل للفترة المحددة.
    """
    # 1. جلب الإيرادات (Revenues) - الأرصدة الدائنة ناقص المدينة
    revenues = Account.objects.filter(code__startswith="4")
    revenue_data = []
    total_revenue = Decimal("0.00")

    for acc in revenues:
        items = JournalItem.objects.filter(
            account=acc, journal_entry__entry_date__range=(start_date, end_date)
        ).aggregate(debit=Sum("debit"), credit=Sum("credit"))
        balance = (items["credit"] or Decimal("0.00")) - (
            items["debit"] or Decimal("0.00")
        )
        if balance != 0:
            revenue_data.append(
                {"code": acc.code, "name": acc.name, "balance": balance}
            )
            total_revenue += balance

    # 2. جلب المصروفات (Expenses) - الأرصدة المدينة ناقص الدائنة
    expenses = Account.objects.filter(code__startswith="3")
    expense_data = []
    total_expense = Decimal("0.00")

    for acc in expenses:
        items = JournalItem.objects.filter(
            account=acc, journal_entry__entry_date__range=(start_date, end_date)
        ).aggregate(debit=Sum("debit"), credit=Sum("credit"))
        balance = (items["debit"] or Decimal("0.00")) - (
            items["credit"] or Decimal("0.00")
        )
        if balance != 0:
            expense_data.append(
                {"code": acc.code, "name": acc.name, "balance": balance}
            )
            total_expense += balance

    # 3. صافي الدخل
    net_income = total_revenue - total_expense

    return {
        "period": f"{start_date} to {end_date}",
        "revenues": revenue_data,
        "total_revenue": total_revenue,
        "expenses": expense_data,
        "total_expense": total_expense,
        "net_income": net_income,
    }
