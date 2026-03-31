# PATH: apps/accounting/admin.py
from decimal import Decimal
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
# --- حاشية: نحتاج تجميع المصروفات وعدّها حسب السيارة ---
from django.db.models import Sum, Count
# --- حاشية: نحتاج صفحة Template داخل الـ admin للتقرير ---
from django.template.response import TemplateResponse
# --- حاشية: نحتاج مسار داخلي وزر يفتح صفحة التقرير ---
from django.urls import path, reverse
from django.utils.html import format_html
# --- حاشية: نضيف resources لتعريف Resource خاص بالمصروفات وإظهار زر التصدير ---
from import_export import resources
from import_export.admin import ImportExportModelAdmin
# --- حاشية: أضفنا Sum لحساب السيارة الأعلى إجماليًا بالمصاريف داخل الفلتر المخصص ---
from django.db.models import Sum
from core.admin_site import custom_admin_site
from .resources import AccountResource
from .services import post_expense, post_revenue
from apps.attachments.inlines import AttachmentInline


from .models import (
    Account,
    JournalEntry,
    JournalItem,
    Expense,
    ExpenseAttachment,
    EntryState,
    Revenue,
)
from django.forms.models import BaseInlineFormSet
from django.utils.dateparse import parse_date
from datetime import timedelta

class JournalItemInlineFormSet(BaseInlineFormSet):
    def clean(self):
        # تنفيذ تحقق Django الأساسي أولًا.
        super().clean()

        # --- حاشية: سنجمع المدين والدائن من السطور غير المحذوفة فقط ---
        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        has_at_least_one_line = False

        for form in self.forms:
            # --- حاشية: إذا كان الفورم نفسه غير صالح نخرج ونترك الأخطاء الأصلية تظهر ---
            if not hasattr(form, "cleaned_data"):
                continue

            cleaned_data = form.cleaned_data

            # --- حاشية: تجاهل السطور الفارغة أو التي اختار المستخدم حذفها ---
            if not cleaned_data or cleaned_data.get("DELETE", False):
                continue

            account = cleaned_data.get("account")
            debit = cleaned_data.get("debit") or Decimal("0.00")
            credit = cleaned_data.get("credit") or Decimal("0.00")

            # --- حاشية: لا نحسب السطر إذا لم يتم اختيار حساب بعد ---
            if not account:
                continue

            has_at_least_one_line = True
            total_debit += debit
            total_credit += credit

        # --- حاشية: ممنوع حفظ القيد إذا لم يتم إدخال أي سطر محاسبي فعلي ---
        if not has_at_least_one_line:
            raise ValidationError(
                "Cannot save journal entry without at least one journal line."
            )

        # --- حاشية: بعد التأكد من وجود سطور فعلية يجب أن يكون القيد متوازنًا ---
        if total_debit != total_credit:
            raise ValidationError(
                f"Journal entry is unbalanced. Debit={total_debit}, Credit={total_credit}"
            )


# هذا الـ inline مسؤول عن أسطر القيود داخل شاشة القيد الرئيسي.
class JournalItemInline(admin.TabularInline):
    # ربط الـ inline بموديل عناصر القيد.
    model = JournalItem
    formset = JournalItemInlineFormSet
    # لا نضيف أسطر وهمية افتراضيًا.
    extra = 0
    # الحقول الظاهرة داخل الصف.
    fields = ("account", "description", "debit", "credit")
    # تفعيل البحث التلقائي للحسابات.
    autocomplete_fields = ("account",)

    def has_add_permission(self, request, obj=None):
        # إذا كان القيد مرحلًا فلا نسمح بإضافة أسطر جديدة.
        if obj and obj.state == EntryState.POSTED:
            return False
        # خلاف ذلك نرجع إلى سلوك Django الافتراضي.
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # إذا كان القيد مرحلًا فلا نسمح بحذف أسطره.
        if obj and obj.state == EntryState.POSTED:
            return False
        # خلاف ذلك نرجع إلى سلوك Django الافتراضي.
        return super().has_delete_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        # بعد الترحيل تصبح كل حقول السطر للقراءة فقط.
        if obj and obj.state == EntryState.POSTED:
            return ("account", "description", "debit", "credit")
        # قبل الترحيل تبقى قابلة للتحرير.
        return ()


@admin.register(Account, site=custom_admin_site)
class AccountAdmin(ImportExportModelAdmin):
    # الأعمدة الظاهرة في قائمة الحسابات.
    list_display = (
        "code",
        "name",
        "account_type",
        "parent",
        "is_postable",
        "is_active",
        "balance_display",
    )
    # الفلاتر الجانبية.
    list_filter = ("account_type", "is_postable", "is_active")
    # حقول البحث.
    search_fields = ("code", "name")
    # الترتيب الافتراضي.
    ordering = ("code",)
    # تحسين الاستعلامات عند جلب الأب.
    list_select_related = ("parent",)
    # ربط الاستيراد/التصدير.
    resource_class = AccountResource

    # تقسيم الحقول داخل صفحة الحساب.
    fieldsets = (
        ("Basic Information", {"fields": ("code", "name", "account_type")}),
        ("Structure", {"fields": ("parent", "is_postable", "is_active")}),
    )

    def balance_display(self, obj):
        # عرض الرصيد المحسوب من خاصية الموديل.
        return obj.balance

    # اسم العمود في الواجهة.
    balance_display.short_description = "Balance"


@admin.register(JournalEntry, site=custom_admin_site)
class JournalEntryAdmin(admin.ModelAdmin):
    # الأعمدة الظاهرة في قائمة القيود اليومية.
    list_display = (
        "entry_no",
        "entry_date",
        "description",
        "state",
        "total_debit",
        "total_credit",
        "source_link",
        "posted_at",
    )
    # الفلاتر الجانبية.
    list_filter = ("state", "entry_date", "source_app", "source_model")
    # الحقول المعتمدة في البحث.
    search_fields = (
        "entry_no",
        "description",
        "source_app",
        "source_model",
        "source_id",
    )
    # تفعيل شريط التواريخ.
    date_hierarchy = "entry_date"
    # إظهار عناصر القيد داخل نفس الشاشة.
    inlines = [JournalItemInline, AttachmentInline]
    # هذه الحقول دائمًا للقراءة فقط لأن أرقام الترقيم والمجاميع تُولد/تُحسب آليًا.
    readonly_fields = (
        "entry_no",
        "total_debit_display",
        "total_credit_display",
        "is_balanced_display",
        "posted_at",
        "source_app",
        "source_model",
        "source_id",
    )

    # تقسيم الحقول داخل شاشة القيد.
    fieldsets = (
        (
            "Journal Entry",
            {
                "fields": (
                    "entry_no",
                    "entry_date",
                    "description",
                    "state",
                    "posted_at",
                )
            },
        ),
        (
            "Totals",
            {
                "fields": (
                    "total_debit_display",
                    "total_credit_display",
                    "is_balanced_display",
                )
            },
        ),
        (
            "Source Reference",
            {
                "fields": (
                    "source_app",
                    "source_model",
                    "source_id",
                )
            },
        ),
    )

    # الإجراء الجماعي لترحيل القيود.
    # الإجراء الجماعي لترحيل القيود.
    actions = ("post_selected_entries",)

    # --- حاشية: قالب مخصص لإظهار فلتر التاريخ أعلى صفحة القيود مثل العقود ---
    change_list_template = "admin/accounting/journalentry/change_list.html"

    def changelist_view(self, request, extra_context=None):
        # --- حاشية: نلتقط قيم فلتر التاريخ المخصص قبل أن يتعامل معها Django Admin ---
        journal_date_from = request.GET.get("journal_date_from")
        journal_date_to = request.GET.get("journal_date_to")

        # --- حاشية: نمرر القيم إلى القالب حتى تبقى ظاهرة بعد الضغط على Apply ---
        extra_context = extra_context or {}
        extra_context["journal_date_from"] = journal_date_from or ""
        extra_context["journal_date_to"] = journal_date_to or ""

        # --- حاشية: نحافظ على بقية الفلاتر والبحث عند إرسال فورم التاريخ ---
        preserved_params = []
        for key, values in request.GET.lists():
            if key in {"journal_date_from", "journal_date_to", "p"}:
                continue

            for value in values:
                preserved_params.append((key, value))

        extra_context["journal_date_preserved_params"] = preserved_params

        # --- حاشية: نحذف بارامترات التاريخ المخصصة من GET ---
        # --- حتى لا يعتبرها Django Admin lookup غير معروف ---
        cleaned_get = request.GET.copy()
        cleaned_get.pop("journal_date_from", None)
        cleaned_get.pop("journal_date_to", None)
        request.GET = cleaned_get

        # --- حاشية: نخزن القيم في request لاستخدامها داخل get_queryset ---
        request._journal_date_from = journal_date_from
        request._journal_date_to = journal_date_to

        return super().changelist_view(request, extra_context=extra_context)

    def get_queryset(self, request):
        # --- حاشية: نبدأ من queryset الإدارة الطبيعي ---
        qs = super().get_queryset(request)

        # --- حاشية: نقرأ قيم التاريخ من الخصائص التي خزناها داخل changelist_view ---
        from_value = getattr(request, "_journal_date_from", None) or request.GET.get(
            "journal_date_from"
        )
        to_value = getattr(request, "_journal_date_to", None) or request.GET.get(
            "journal_date_to"
        )

        from_date = parse_date(from_value) if from_value else None
        to_date = parse_date(to_value) if to_value else None

        # --- حاشية: من تاريخ البداية بشكل شامل ---
        if from_date:
            qs = qs.filter(entry_date__gte=from_date)

        # --- حاشية: إلى نهاية تاريخ النهاية بشكل صحيح ---
        # --- نستخدم أقل من اليوم التالي حتى تعمل سواء كان الحقل Date أو DateTime ---
        if to_date:
            qs = qs.filter(entry_date__lt=to_date + timedelta(days=1))

        return qs

    def get_actions(self, request):
        # --- إزالة الحذف الجماعي الافتراضي لأنه قد يتجاوز delete() في الموديل ---
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    def total_debit_display(self, obj):
        # إرجاع مجموع المدين.
        return obj.total_debit

    # تسمية عمود مجموع المدين.
    total_debit_display.short_description = "Total Debit"

    def total_credit_display(self, obj):
        # إرجاع مجموع الدائن.
        return obj.total_credit

    # تسمية عمود مجموع الدائن.
    total_credit_display.short_description = "Total Credit"

    def is_balanced_display(self, obj):
        # عند توازن القيد نعرض تنسيقًا أخضر.
        if obj.is_balanced:
            return format_html(
                '<span style="color: green; font-weight: 600;">{}</span>',
                "Balanced",
            )
        # وإذا كان غير متوازن نعرض تنسيقًا أحمر.
        return format_html(
            '<span style="color: red; font-weight: 600;">{}</span>',
            "Unbalanced",
        )

    # تسمية عمود التوازن.
    is_balanced_display.short_description = "Balanced?"

    def source_link(self, obj):
        # إظهار المصدر النصي إذا كانت معلومات المصدر موجودة.
        if obj.source_model and obj.source_id:
            return f"{obj.source_model} #{obj.source_id}"
        # وإلا نعرض شرطة بديلة.
        return "-"

    # تسمية عمود المصدر.
    source_link.short_description = "Source"

    def has_delete_permission(self, request, obj=None):
        # منع حذف القيد بعد ترحيله.
        if obj and obj.state == EntryState.POSTED:
            return False
        # خلاف ذلك نرجع إلى السلوك الافتراضي.
        return super().has_delete_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        # نبدأ دائمًا من الحقول الأساسية المقروءة فقط.
        base_fields = list(self.readonly_fields)

        # --- حاشية: نقفل state دائمًا من شاشة الفورم ---
        # --- حتى يبدأ القيد Draft دائمًا ولا يتم ترحيله إلا من Action الـ Post ---
        if "state" not in base_fields:
            base_fields.append("state")

        # بعد الترحيل تصبح الحقول التحريرية الأساسية للقراءة فقط أيضًا.
        if obj and obj.state == EntryState.POSTED:
            base_fields.extend(["entry_date", "description"])

        # إعادة القائمة النهائية كـ tuple.
        return tuple(base_fields)

    def save_model(self, request, obj, form, change):
        # --- حاشية: عند إنشاء قيد جديد نفرض الحالة دائمًا Draft ---
        # --- ولا نسمح بتحديد Posted يدويًا من شاشة الإدخال ---
        if not change:
            obj.state = EntryState.DRAFT
            super().save_model(request, obj, form, change)
            return

        # --- حاشية: عند التعديل نقرأ النسخة القديمة من قاعدة البيانات ---
        old_obj = JournalEntry.objects.get(pk=obj.pk)

        # --- حاشية: إذا كان القيد مرحلًا نمنع أي تعديل فعلي ---
        if old_obj.state == EntryState.POSTED:
            if form.changed_data:
                raise ValidationError("Posted journal entries cannot be edited.")
            return

        # --- حاشية: نمنع تغيير الحالة يدويًا من شاشة الفورم ---
        # --- تبقى Draft إلى أن يتم الترحيل فقط عبر Action الـ Post ---
        obj.state = old_obj.state

        # --- حاشية: الحفظ الطبيعي لبقية الحقول ---
        super().save_model(request, obj, form, change)

    @admin.action(description="Post selected journal entries")
    def post_selected_entries(self, request, queryset):
        # عداد للقيود التي تم ترحيلها بنجاح.
        posted_count = 0

        # المرور على القيود المحددة.
        for entry in queryset:
            try:
                # إذا كان القيد مرحلًا أصلًا نتجاوزه.
                if entry.state == EntryState.POSTED:
                    continue
                # محاولة ترحيل القيد.
                entry.post()
                # زيادة العداد بعد النجاح.
                posted_count += 1
            except Exception as exc:
                # في حال وجود خطأ نعرض رسالة واضحة للمستخدم.
                self.message_user(
                    request,
                    f"Entry {entry.entry_no} was not posted: {exc}",
                    level=messages.ERROR,
                )

        # إذا تم ترحيل أي قيد بنجاح نعرض رسالة نجاح.
        if posted_count:
            self.message_user(
                request,
                f"{posted_count} journal entr{'y' if posted_count == 1 else 'ies'} posted successfully.",
                level=messages.SUCCESS,
            )
    class Media:
        css = {
            "all": (
                "css/attachment_gallery_inline.css",
                
            )
        }

        js = (
            "js/attachment_gallery_inline.js",
        )       


class ExpenseResource(resources.ModelResource):
    class Meta:
        model = Expense
        fields = (
            "id",
            "reference",
            "expense_date",
            "category",
            "description",
            "amount",
            "payment_method",
            "vehicle",
            "branch",
            "expense_account",
            "state",
            "journal_entry",
        )
        export_order = fields


@admin.register(Expense, site=custom_admin_site)
class ExpenseAdmin(ImportExportModelAdmin):
    resource_class = ExpenseResource

    # --- حاشية: هذا القالب يضيف زر تقرير ترتيب السيارات داخل صفحة المصروفات ---
    change_list_template = "admin/accounting/expense/change_list.html"

    # الأعمدة الظاهرة في قائمة المصروفات.
    list_display = (
        "reference",
        "expense_date",
        "category",
        "description",
        "amount",
        "payment_method",
        "vehicle_plate_number",
        "state",
        "journal_entry_link",
    )

    # --- حاشية: أبقينا فقط الفلاتر العادية لأن الترتيب صار عبر زر تقرير مستقل ---
    list_filter = (
        "state",
        "category",
        "payment_method",
        "expense_date",
    )

    # حقول البحث.
    search_fields = (
        "reference",
        "description",
        "vehicle__plate_number",
        "vehicle__brand",
        "vehicle__model",
    )

    # تفعيل شريط التاريخ.
    date_hierarchy = "expense_date"

    # البحث التلقائي في حساب المصروف.
    autocomplete_fields = ("expense_account",)

    # المرجع والقيد الناتج حقول آلية للقراءة فقط.
    readonly_fields = ("reference", "journal_entry")

    # الإجراء الجماعي للترحيل.
    actions = ("post_selected_expenses",)

    # إظهار المرفقات داخل شاشة المصروف.
    inlines = [AttachmentInline]

    # تقسيم الحقول داخل الصفحة.
    fieldsets = (
        (
            "Expense",
            {
                "fields": (
                    "reference",
                    "expense_date",
                    "category",
                    "description",
                    "amount",
                    "payment_method",
                )
            },
        ),
        (
            "Classification",
            {
                "fields": (
                    "expense_account",
                    "vehicle",
                    "branch",
                )
            },
        ),
        (
            "Accounting",
            {
                "fields": (
                    "state",
                    "journal_entry",
                )
            },
        ),
    )

    # --- حاشية: إضافة رابط admin مخصص لصفحة ترتيب السيارات حسب مجموع المصروفات ---
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "vehicle-expense-ranking/",
                self.admin_site.admin_view(self.vehicle_expense_ranking_view),
                name="accounting_expense_vehicle_expense_ranking",
            ),
        ]
        return custom_urls + urls

    # --- حاشية: تمرير رابط التقرير إلى صفحة قائمة المصروفات لإظهار الزر ---
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["vehicle_expense_ranking_url"] = reverse(
            "admin:accounting_expense_vehicle_expense_ranking"
        )
        return super().changelist_view(request, extra_context=extra_context)

    # --- حاشية: صفحة تقرير ترتّب السيارات من الأعلى مصروفًا إلى الأقل ضمن فترة اختيارية ---
    def vehicle_expense_ranking_view(self, request):
        # --- حاشية: قراءة تاريخ البداية والنهاية من الرابط ---
        from_date = request.GET.get("from_date")
        to_date = request.GET.get("to_date")

        # --- حاشية: نأخذ فقط المصروفات المرتبطة بسيارة ---
        queryset = Expense.objects.filter(
            vehicle__isnull=False,
            state=EntryState.POSTED,
        )

        # --- حاشية: تطبيق فلترة الفترة إذا تم إدخالها ---
        if from_date:
            queryset = queryset.filter(expense_date__gte=from_date)

        if to_date:
            queryset = queryset.filter(expense_date__lte=to_date)

        # --- حاشية: تجميع المصروفات حسب السيارة وترتيبها من الأعلى إلى الأقل ---
        ranking = (
            queryset.values(
                "vehicle_id",
                "vehicle__plate_number",
                "vehicle__brand",
                "vehicle__model",
                "vehicle__branch__name",
            )
            .annotate(
                total_expense=Sum("amount"),
                expense_count=Count("id"),
            )
            .order_by("-total_expense", "vehicle__plate_number")
        )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Vehicle Expense Ranking",
            "ranking": ranking,
            "from_date": from_date,
            "to_date": to_date,
            "back_url": reverse("admin:accounting_expense_changelist"),
        }

        return TemplateResponse(
            request,
            "admin/accounting/expense/vehicle_expense_ranking.html",
            context,
        )

    # --- حاشية: هذه الدالة تعرض رقم السيارة فقط داخل قائمة المصروفات ---
    def vehicle_plate_number(self, obj):
        if obj.vehicle_id:
            return obj.vehicle.plate_number
        return "-"

    # --- حاشية: اسم العمود الظاهر في صفحة القائمة ---
    vehicle_plate_number.short_description = "Vehicle No"

    def journal_entry_link(self, obj):
        # عند وجود قيد مرتبط نعرض رقمه.
        if obj.journal_entry_id:
            return obj.journal_entry.entry_no
        # وإذا لم يوجد نعرض شرطة.
        return "-"

    # تسمية عمود القيد.
    journal_entry_link.short_description = "Journal Entry"

    def get_actions(self, request):
        # --- إزالة الحذف الجماعي الافتراضي لأنه قد يتجاوز delete() في الموديل ---
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    def has_delete_permission(self, request, obj=None):
        # منع حذف المصروف إذا كان مرحلًا.
        if obj and obj.state == EntryState.POSTED:
            return False
        return super().has_delete_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        # نبدأ من الحقول الأساسية للقراءة فقط.
        base_fields = list(self.readonly_fields)

        # --- حاشية: نقفل state دائمًا من شاشة الفورم ---
        # --- لأن الترحيل يجب أن يتم فقط من Action الـ Post وليس يدويًا من الشاشة ---
        if "state" not in base_fields:
            base_fields.append("state")

        # بعد الترحيل تصبح كل حقول المصروف الحساسة للقراءة فقط.
        if obj and obj.state == EntryState.POSTED:
            base_fields.extend(
                [
                    "expense_date",
                    "category",
                    "description",
                    "amount",
                    "payment_method",
                    "expense_account",
                    "vehicle",
                    "branch",
                ]
            )

        # إعادة النتيجة النهائية.
        return tuple(base_fields)

    def save_model(self, request, obj, form, change):
        # --- حاشية: عند إنشاء مصروف جديد نفرض الحالة دائمًا Draft ---
        # --- حتى يكون الترحيل لاحقًا فقط عبر Action الـ Post ---
        if not change:
            obj.state = EntryState.DRAFT
            super().save_model(request, obj, form, change)
            return

        # --- حاشية: عند تعديل مصروف موجود نقرأ النسخة القديمة من قاعدة البيانات ---
        old_obj = Expense.objects.get(pk=obj.pk)

        # --- حاشية: إذا كان السجل مرحلًا أصلًا نمنع أي تعديل فعلي ---
        if old_obj.state == EntryState.POSTED:
            if form.changed_data:
                raise ValidationError("Posted expenses cannot be edited.")
            return

        # --- حاشية: نمنع أي محاولة لتغيير الحالة يدويًا من شاشة الفورم ---
        # --- لأن إنشاء القيد يجب أن يمر فقط عبر post_expense داخل Action الـ Post ---
        obj.state = old_obj.state

        # --- حاشية: الحفظ الطبيعي لبقية الحقول بدون السماح بتغيير state يدويًا ---
        super().save_model(request, obj, form, change)

    @admin.action(description="Post selected expenses")
    def post_selected_expenses(self, request, queryset):
        # عداد لعدد المصروفات المرحلة بنجاح.
        posted_count = 0

        for expense in queryset:
            try:
                if expense.state == EntryState.POSTED:
                    continue
                post_expense(expense=expense)
                posted_count += 1
            except Exception as exc:
                self.message_user(
                    request,
                    f"Expense {expense.reference} was not posted: {exc}",
                    level=messages.ERROR,
                )

        if posted_count:
            self.message_user(
                request,
                f"{posted_count} expense record{' was' if posted_count == 1 else 's were'} posted successfully.",
                level=messages.SUCCESS,
            )

    class Media:
        css = {"all": ("css/attachment_gallery_inline.css",)}

        js = ("js/attachment_gallery_inline.js",)


@admin.register(Revenue, site=custom_admin_site)
class RevenueAdmin(admin.ModelAdmin):
    # الأعمدة الظاهرة في قائمة الإيرادات.
    list_display = (
        "reference",
        "revenue_date",
        "category",
        "description",
        "amount",
        "payment_method",
        "vehicle",
        "branch",
        "state",
        "journal_entry_link",
    )
    # الفلاتر الجانبية.
    list_filter = (
        "state",
        "category",
        "payment_method",
        "revenue_date",
        "vehicle",
        "branch",
    )
    # حقول البحث.
    search_fields = (
        "reference",
        "description",
        "vehicle__plate_number",
        "branch__name",
    )
    # تفعيل شريط التاريخ.
    date_hierarchy = "revenue_date"
    # البحث التلقائي لحساب الإيراد.
    autocomplete_fields = ("revenue_account",)
    # المرجع والقيد الناتج حقول آلية للقراءة فقط.
    readonly_fields = ("reference", "journal_entry")
    # الإجراء الجماعي لترحيل الإيرادات.
    actions = ("post_selected_revenues",)

    # عرض المرفقات العامة داخل نفس شاشة الإيراد
    inlines = [AttachmentInline]

    class Media:
        css = {"all": ("css/attachment_gallery_inline.css",)}

        js = ("js/attachment_gallery_inline.js",)

    # تقسيم الحقول داخل الصفحة.
    fieldsets = (
        (
            "Revenue",
            {
                "fields": (
                    "reference",
                    "revenue_date",
                    "category",
                    "description",
                    "amount",
                    "payment_method",
                )
            },
        ),
        (
            "Classification",
            {
                "fields": (
                    "revenue_account",
                    "vehicle",
                    "branch",
                )
            },
        ),
        (
            "Accounting",
            {
                "fields": (
                    "state",
                    "journal_entry",
                )
            },
        ),
    )

    def journal_entry_link(self, obj):
        # عند وجود قيد مرتبط نعرض رقمه.
        if obj.journal_entry_id:
            return obj.journal_entry.entry_no
        # وإلا نعرض شرطة.
        return "-"

    def delete_queryset(self, request, queryset):
        # بدلاً من الحذف المباشر بقاعدة البيانات الذي يتخطى الموديل
        # نقوم بالمرور على السجلات لحذفها فرادى لتمر عبر حماية الموديل
        for obj in queryset:
            obj.delete()    

    def get_actions(self, request):
        # --- إزالة الحذف الجماعي الافتراضي لأنه قد يتجاوز delete() في الموديل ---
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    # تسمية العمود.
    journal_entry_link.short_description = "Journal Entry"

    def has_delete_permission(self, request, obj=None):
        # منع حذف الإيراد بعد ترحيله.
        if obj and obj.state == EntryState.POSTED:
            return False
        # خلاف ذلك نرجع للسلوك الافتراضي.
        return super().has_delete_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        # نبدأ من الحقول الأساسية المقروءة فقط.
        base_fields = list(self.readonly_fields)

        # --- حاشية: نقفل state دائمًا من شاشة الفورم ---
        # --- حتى يكون الترحيل فقط من Action الـ Post وليس يدويًا ---
        if "state" not in base_fields:
            base_fields.append("state")

        # بعد الترحيل تصبح بقية الحقول التشغيلية والمحاسبية للقراءة فقط.
        if obj and obj.state == EntryState.POSTED:
            base_fields.extend(
                [
                    "revenue_date",
                    "category",
                    "description",
                    "amount",
                    "payment_method",
                    "revenue_account",
                    "vehicle",
                    "branch",
                ]
            )

        return tuple(base_fields)

    # 1. التعديل في: apps/accounting/admin.py
    # يجب تنظيف الدالة لتبقى للحفظ الافتراضي فقط (أو حذفها كلياً إن لم يكن لها استخدام آخر)
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

    # 2. التعديل في: apps/accounting/models.py (داخل كلاس Revenue)
    def clean(self):
        super().clean()

        # إضافة الفحص هنا ليتم عرضه كرسالة خطأ سلسة للمستخدم
        # نتحقق فقط في حالة التعديل (السجل موجود مسبقاً)
        if self.pk:
            old_obj = self.__class__.objects.get(pk=self.pk)
            if old_obj.state == EntryState.POSTED:
                raise ValidationError("Posted records cannot be edited.")

        # ... (بقاء باقي كود clean الحالي الخاص بك لفحص المبلغ ونوع الحساب كما هو) ...

    @admin.action(description="Post selected revenues")
    def post_selected_revenues(self, request, queryset):
        # عداد لعدد الإيرادات المرحلة.
        posted_count = 0

        # المرور على العناصر المحددة.
        for revenue in queryset:
            try:
                # إذا كان الإيراد مرحلًا أصلًا نتجاوزه.
                if revenue.state == EntryState.POSTED:
                    continue
                # محاولة ترحيل الإيراد.
                post_revenue(revenue=revenue)
                # زيادة العداد بعد النجاح.
                posted_count += 1
            except Exception as exc:
                # عرض رسالة خطأ واضحة للمستخدم.
                self.message_user(
                    request,
                    f"Revenue {revenue.reference} was not posted: {exc}",
                    level=messages.ERROR,
                )

        # عرض رسالة نجاح إن تم ترحيل عناصر.
        if posted_count:
            self.message_user(
                request,
                f"{posted_count} revenue record{' was' if posted_count == 1 else 's were'} posted successfully.",
                level=messages.SUCCESS,
            )
