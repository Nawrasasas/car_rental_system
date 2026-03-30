# PATH: apps/rentals/admin.py
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.db.models import Sum, F, Value, DecimalField, ExpressionWrapper, Q
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.apps import apps
from apps.vehicles.models import Vehicle
from import_export.admin import ExportActionModelAdmin
from .models import Rental, RentalLog
from apps.attachments.inlines import AttachmentInline
from apps.payments.models import Payment
from django import forms
from core.admin_site import custom_admin_site
from decimal import Decimal
from django.db import transaction
from django.forms.models import BaseInlineFormSet
from django.utils.dateparse import parse_date
from datetime import datetime, time, timedelta


class RentalLogInline(admin.TabularInline):
    # عرض سجل العمليات داخل صفحة العقد
    model = RentalLog
    extra = 0
    can_delete = False
    readonly_fields = ('action', 'details', 'user', 'created_at')

    def has_add_permission(self, request, obj=None):
        # منع إضافة سجل يدويًا من الإدارة
        return False


class PaymentStatusFilter(admin.SimpleListFilter):
    # فلتر جانبي لحالة الدفع
    title = 'By Payment Status'
    parameter_name = 'payment_status'

    def lookups(self, request, model_admin):
        return (
            ('unpaid', 'Unpaid (Has Balance)'),
            ('paid', 'Fully Paid'),
        )

    def queryset(self, request, queryset):
        value = self.value()

        paid_total = Coalesce(
            Sum('payments__amount_paid'),
            Value(0),
            output_field=DecimalField(max_digits=10, decimal_places=2),
        )

        qs = queryset.annotate(
            paid_total=paid_total,
            remaining_due=ExpressionWrapper(
                F('net_total') - paid_total,
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        )

        if value == 'unpaid':
            return qs.filter(remaining_due__gt=0)

        if value == 'paid':
            return qs.filter(remaining_due__lte=0)

        return qs


class RentalStatusFilter(admin.SimpleListFilter):
    # فلتر جانبي لحالة العقد الفعلية
    title = 'By Rental Status'
    parameter_name = 'rental_status'

    def lookups(self, request, model_admin):
        return (
            ('active', 'Active'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
            ('overdue', 'Overdue'),
        )

    def queryset(self, request, queryset):
        value = self.value()

        if value == 'active':
            return queryset.filter(status='active', actual_return_date__isnull=True)

        if value == 'completed':
            return queryset.filter(status='completed')

        if value == 'cancelled':
            return queryset.filter(status='cancelled')

        if value == 'overdue':
            return queryset.filter(
                status='active',
                actual_return_date__isnull=True,
                end_date__lt=timezone.now(),
            )

        return queryset


class RentalAdminForm(forms.ModelForm):
    initial_payment_amount = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=10,
        decimal_places=2,
        label="Initial Payment Amount",
    )

    initial_payment_method = forms.ChoiceField(
        required=False,
        choices=Payment._meta.get_field("method").choices,
        label="Initial Payment Method",
    )

    initial_payment_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        label="Initial Payment Notes",
    )

    class Meta:
        model = Rental
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()

        customer = cleaned_data.get("customer")
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        pickup_odometer = cleaned_data.get("pickup_odometer")
        return_odometer = cleaned_data.get("return_odometer")
        initial_payment_amount = cleaned_data.get("initial_payment_amount")
        initial_payment_method = cleaned_data.get("initial_payment_method")

        if not self.instance.pk and end_date and end_date < timezone.now():
            raise forms.ValidationError(
                "Cannot create a contract with an end date in the past."
            )

        if customer and start_date:
            # --- منع إنشاء/حفظ العقد إذا كان جواز السفر منتهيًا ---
            passport_expiry_date = getattr(customer, "passport_expiry_date", None)
            if passport_expiry_date and passport_expiry_date <= start_date.date():
                raise forms.ValidationError(
                    "Cannot create this contract because the customer's passport is expired at or before the pickup date."
                )

            # --- منع إنشاء/حفظ العقد إذا كانت شهادة السواقة منتهية ---
            driving_license_expiry_date = getattr(
                customer,
                "driving_license_expiry_date",
                None,
            )
            if (
                driving_license_expiry_date
                and driving_license_expiry_date <= start_date.date()
            ):
                raise forms.ValidationError(
                    "Cannot create this contract because the customer's driving license is expired at or before the pickup date."
                )

        if pickup_odometer is not None and return_odometer is not None:
            if return_odometer < pickup_odometer:
                raise forms.ValidationError(
                    "Return odometer cannot be less than pickup odometer."
                )

        # --- إذا أدخل المستخدم مبلغ دفعة أولية
        # --- يجب أن يحدد طريقة الدفع أيضًا ---
        if (
            initial_payment_amount
            and initial_payment_amount > 0
            and not initial_payment_method
        ):
            self.add_error(
                "initial_payment_method",
                "Initial payment method is required when initial payment amount is entered.",
            )

        daily_rate = cleaned_data.get("daily_rate") or Decimal("0.00")
        vat_percentage = cleaned_data.get("vat_percentage") or Decimal("0.00")
        deposit_amount = cleaned_data.get("deposit_amount") or Decimal("0.00")
        traffic_fines = cleaned_data.get("traffic_fines") or Decimal("0.00")
        damage_fees = cleaned_data.get("damage_fees") or Decimal("0.00")
        other_charges = cleaned_data.get("other_charges") or Decimal("0.00")

        if start_date and end_date and end_date >= start_date:
            # --- نهمل الدقائق والثواني والمايكروثانية ---
            # --- حتى يطابق تقدير الفورم الحسبة الفعلية في الموديل ---
            start_hour = start_date.replace(minute=0, second=0, microsecond=0)
            end_hour = end_date.replace(minute=0, second=0, microsecond=0)

            seconds = (end_hour - start_hour).total_seconds()
            rental_days = max(1, int(seconds // 86400))
            if seconds % 86400:
                rental_days += 1

            subtotal = Decimal(daily_rate) * Decimal(rental_days)
            vat_amount = (subtotal * Decimal(vat_percentage)) / Decimal("100")
            # --- Net Total الظاهري النهائي ---
            # --- يشمل التأمين أيضًا لأنه جزء مما يجب أن يدفعه الزبون ---
            estimated_total = (
                subtotal
                + vat_amount
                + traffic_fines
                + damage_fees
                + other_charges
                + deposit_amount
            )

            if (
                initial_payment_amount is not None
                and initial_payment_amount > estimated_total
            ):
                raise forms.ValidationError(
                    f"Initial payment cannot be greater than the contract total ({estimated_total})."
                )

        return cleaned_data


class PaymentInlineFormSet(BaseInlineFormSet):
    """
    هذا الفورم مسؤول عن تجربة المستخدم (UX) في لوحة التحكم،
    يمنع إدخال دفعات أكبر من العقد ويظهر رسالة خطأ حمراء أنيقة.
    """
    def clean(self):
        super().clean()
        
        # إذا كانت هناك أخطاء أخرى في الحقول، لا نكمل الفحص
        if any(self.errors):
            return

        # جلب قيمة العقد الصافية
        contract_total = getattr(self.instance, 'net_total', Decimal("0.00")) or Decimal("0.00")
        
        # 1. حساب مجموع الدفعات المدخلة حالياً في الشاشة
        total_paid_in_form = Decimal("0.00")
        for form in self.forms:
            # تجاهل السطور التي ضغط المستخدم على زر حذفها
            if self.can_delete and self._should_delete_form(form):
                continue
            
            amount = form.cleaned_data.get('amount_paid', Decimal("0.00")) or Decimal("0.00")
            total_paid_in_form += amount

        # 2. حساب الدفعات السابقة المحفوظة في قاعدة البيانات (في حال تعديل عقد قديم)
        existing_total = Decimal("0.00")
        if self.instance.pk:
            from apps.payments.models import Payment
            # نستثني الدفعات المفتوحة حالياً في الشاشة حتى لا نحسبها مرتين
            form_instance_ids = [f.instance.id for f in self.forms if f.instance.id]
            existing_total = Payment.objects.filter(rental=self.instance).exclude(
                id__in=form_instance_ids
            ).aggregate(total=Sum("amount_paid"))["total"] or Decimal("0.00")

        final_total = total_paid_in_form + existing_total

        # 3. إظهار رسالة الخطأ الأنيقة
        if final_total > contract_total:
            raise ValidationError(
                f"❌ غير مسموح: مجموع الدفعات ({final_total}) يتجاوز صافي قيمة العقد ({contract_total})."
            )

# تأكد من ربط هذا الـ FormSet بالـ Inline الخاص بالدفعات في نفس الملف
# class PaymentInline(admin.TabularInline):
#     model = Payment
#     formset = PaymentInlineFormSet

@admin.register(Rental, site=custom_admin_site)
class RentalAdmin(ExportActionModelAdmin, admin.ModelAdmin):
    form = RentalAdminForm
    autocomplete_fields = ('vehicle',)

    # قالب مخصص لإظهار بطاقات حالات العقود أعلى صفحة القائمة
    change_list_template = "admin/rentals/rental/change_list.html"

    def changelist_view(self, request, extra_context=None):
        # --- نلتقط قيم فلتر التاريخ قبل أن يتعامل معها Django Admin ---
        contract_date_from = request.GET.get("contract_date_from")
        contract_date_to = request.GET.get("contract_date_to")

        # --- نمرر القيم إلى القالب حتى تبقى ظاهرة بعد الضغط على Apply ---
        extra_context = extra_context or {}
        extra_context["contract_date_from"] = contract_date_from or ""
        extra_context["contract_date_to"] = contract_date_to or ""

        # --- نحافظ على بقية الفلاتر والبحث عند إرسال فورم التاريخ ---
        preserved_params = []
        for key, values in request.GET.lists():
            if key in {"contract_date_from", "contract_date_to", "p"}:
                continue

            for value in values:
                preserved_params.append((key, value))

        extra_context["contract_date_preserved_params"] = preserved_params

        # --- هذه هي النقطة الجوهرية في الحل ---
        # --- نحذف بارامترات التاريخ المخصصة من GET قبل دخول super() ---
        # --- حتى لا يعتبرها Django Admin lookup غير معروف ---
        cleaned_get = request.GET.copy()
        cleaned_get.pop("contract_date_from", None)
        cleaned_get.pop("contract_date_to", None)
        request.GET = cleaned_get

        # --- نخزن القيم في request لاستخدامها داخل get_queryset ---
        request._contract_date_from = contract_date_from
        request._contract_date_to = contract_date_to

        response = super().changelist_view(request, extra_context=extra_context)

        try:
            cl = response.context_data["cl"]
        except (AttributeError, KeyError, TypeError):
            return response

        # --- نفس اسم parameter_name الموجود داخل RentalStatusFilter ---
        filter_param = "rental_status"

        # --- queryset الأساسي للقائمة ---
        base_qs = cl.root_queryset

        # --- نبني روابط البطاقات مع الحفاظ على بقية البارامترات ---
        current_params = request.GET.copy()
        current_params.pop(filter_param, None)
        current_params.pop("p", None)

        # --- نعيد أيضًا بارامترات التاريخ إلى روابط البطاقات ---
        if contract_date_from:
            current_params["contract_date_from"] = contract_date_from
        if contract_date_to:
            current_params["contract_date_to"] = contract_date_to

        current_status = request.GET.get(filter_param)

        def build_url(status_value=None):
            params = current_params.copy()
            if status_value:
                params[filter_param] = status_value
            query_string = params.urlencode()
            return f"{request.path}?{query_string}" if query_string else request.path

        rental_status_cards = [
            {
                "label": "All",
                "count": base_qs.count(),
                "url": build_url(),
                "active": not current_status,
                "css_class": "all",
            },
            {
                "label": "Active",
                "count": base_qs.filter(
                    status="active",
                    actual_return_date__isnull=True,
                ).count(),
                "url": build_url("active"),
                "active": current_status == "active",
                "css_class": "active",
            },
            {
                "label": "Completed",
                "count": base_qs.filter(
                    status="completed",
                ).count(),
                "url": build_url("completed"),
                "active": current_status == "completed",
                "css_class": "completed",
            },
            {
                "label": "Cancelled",
                "count": base_qs.filter(
                    status="cancelled",
                ).count(),
                "url": build_url("cancelled"),
                "active": current_status == "cancelled",
                "css_class": "cancelled",
            },
            {
                "label": "Overdue",
                "count": base_qs.filter(
                    status="active",
                    actual_return_date__isnull=True,
                    end_date__lt=timezone.now(),
                ).count(),
                "url": build_url("overdue"),
                "active": current_status == "overdue",
                "css_class": "overdue",
            },
        ]

        response.context_data["rental_status_cards"] = rental_status_cards
        return response

    def get_queryset(self, request):
        # --- نبدأ من queryset الإدارة الطبيعي ---
        qs = (
            super()
            .get_queryset(request)
            .select_related(
                "customer",
                "vehicle",
                "branch",
                "created_by",
                "journal_entry",
            )
            .prefetch_related(
                "payments",
                "attachments",
                "logs",
            )
        )

        # --- نقرأ قيم التاريخ من الخصائص التي خزناها داخل changelist_view ---
        # --- ونبقي fallback على request.GET تحسبًا لأي استخدام آخر ---
        from_value = getattr(request, "_contract_date_from", None) or request.GET.get(
            "contract_date_from"
        )
        to_value = getattr(request, "_contract_date_to", None) or request.GET.get(
            "contract_date_to"
        )

        from_date = parse_date(from_value) if from_value else None
        to_date = parse_date(to_value) if to_value else None

        current_tz = timezone.get_current_timezone()

        # --- من بداية اليوم المحدد ---
        if from_date:
            from_dt = datetime.combine(from_date, time.min)
            if timezone.is_aware(timezone.now()):
                from_dt = timezone.make_aware(from_dt, current_tz)

            qs = qs.filter(start_date__gte=from_dt)

        # --- إلى بداية اليوم التالي بشكل حصري ---
        if to_date:
            to_dt = datetime.combine(to_date + timedelta(days=1), time.min)
            if timezone.is_aware(timezone.now()):
                to_dt = timezone.make_aware(to_dt, current_tz)

            qs = qs.filter(start_date__lt=to_dt)

        # --- حساب إجمالي الدفعات دفعة واحدة على مستوى قاعدة البيانات ---
        qs = qs.annotate(
            paid_total_db=Coalesce(
                Sum("payments__amount_paid"),
                Value(0),
                output_field=DecimalField(max_digits=10, decimal_places=2),
            )
        )

        return qs
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        هذا الفلتر يفيد فقط في بعض الحالات التقليدية،
        لكن الحماية الأساسية للـ autocomplete ستكون من VehicleAdmin.get_search_results.
        """
        if db_field.name == "vehicle":
            object_id = request.resolver_match.kwargs.get("object_id")

            if object_id:
                try:
                    rental = Rental.objects.only("vehicle_id").get(pk=object_id)
                    kwargs["queryset"] = Vehicle.objects.filter(
                        Q(status="available") | Q(pk=rental.vehicle_id)
                    ).order_by("plate_number")
                except Rental.DoesNotExist:
                    kwargs["queryset"] = Vehicle.objects.filter(
                        status="available"
                    ).order_by("plate_number")
            else:
                kwargs["queryset"] = Vehicle.objects.filter(
                    status="available"
                ).order_by("plate_number")

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # الأعمدة الظاهرة في قائمة العقود
    list_display = (
        "contract_number",
        "get_customer_display",
        "vehicle_info",
        "pickup_time",
        "return_time",
        "grand_total",
        "balance_due",
        "branch",
        "status_label",
        "print_contract_button",
    )

    # الفلاتر الجانبية
    list_filter = (
        PaymentStatusFilter,
        RentalStatusFilter,
        "branch",
        "auto_renew",
        "created_at",
    )

    # البحث
    search_fields = (
        "contract_number",
        "customer__full_name",
        "customer__phone",
        "customer__company_name",
        "vehicle__plate_number",
    )

    # ترتيب افتراضي
    ordering = ('-id',)

    # الحقول المقروءة فقط
    readonly_fields = (
        "rental_days",
        "net_total",
        "created_by",
        "created_at",
        "actual_return_date",
        "post_rental_button",
        "collect_contract_and_deposit_button",
        "collect_traffic_fine_button",
        "return_vehicle_button",
        "print_contract_button",
    )

    # العناصر الداخلية
    inlines = [AttachmentInline ]

    # عدد العناصر في الصفحة
    list_per_page = 25

    class Media:
        css = {
            "all": (
                "css/attachment_gallery_inline.css", 
                "admin/css/rental_admin.css",
            )
        }

        js = (
            "admin/js/rental_calc.js",
            "js/attachment_gallery_inline.js",
        )

    def save_related(self, request, form, formsets, change):
        # --- نحفظ العلاقات العادية فقط مثل المرفقات ---
        # --- مهم: ألغينا تمامًا مسار الدفعة الأولية القديم ---
        # --- حتى لا يبقى لدينا مساران متضاربان للقبض ---
        super().save_related(request, form, formsets, change)

        # --- العقد الذي تم حفظه ---
        rental = form.instance

        # --- بيانات الدفعة الأولية القادمة من الفورم الرئيسي ---
        amount = form.cleaned_data.get("initial_payment_amount")
        method = form.cleaned_data.get("initial_payment_method")
        notes = form.cleaned_data.get("initial_payment_notes")

        # --- ننشئ سجل الدفعة فقط عند إنشاء عقد جديد ---
        # --- مهم جدًا: لا نرحّل أي قيد هنا ---
        if not change and amount is not None and amount > 0:
            if amount > rental.net_total:
                raise ValidationError(
                    f"Initial payment cannot be greater than the contract total ({rental.net_total})."
                )

            payment = Payment(
                rental=rental,
                amount_paid=amount,
                method=method,
                status="completed",
                notes=notes or "",
            )

            # --- نحفظ الدفعة كسجل فقط ---
            # --- وتبقى محاسبيًا Draft حتى الضغط على Post للعقد ---
            payment.full_clean()
            payment.save()

    def save_formset(self, request, form, formset, change):
        # --- إذا لم يكن هذا الـ formset خاصًا بالدفعات ---
        # --- نترك Django يتعامل معه بشكل طبيعي ---
        if formset.model is not Payment:
            return super().save_formset(request, form, formset, change)

        # --- نحصل على العناصر الجديدة/المعدلة بدون حفظ تلقائي ---
        instances = formset.save(commit=False)

        # --- بما أن حذف الدفعات ممنوع في الـ inline فهذا احتياطي فقط ---
        for deleted_obj in formset.deleted_objects:
            deleted_obj.delete()

        # --- نحفظ الدفعات كسجلات فقط بدون أي ترحيل محاسبي ---
        for payment in instances:
            payment.rental = form.instance

            if not payment.status:
                payment.status = "completed"

            # --- مهم: لا نستدعي process_payment هنا ---
            # --- لأن المطلوب ألا يرحّل أي قيد إلا عند Post العقد ---
            payment.full_clean()
            payment.save()

        formset.save_m2m()

    def get_fields(self, request, obj=None):
        fields = [
            "print_contract_button",
            "post_rental_button",
            "collect_contract_and_deposit_button",
            "collect_traffic_fine_button",
            "return_vehicle_button",
            "customer",
            "vehicle",
            "branch",
            "pickup_odometer",
            "return_odometer",
            "start_date",
            "end_date",
            "actual_return_date",
            "daily_rate",
            "deposit_amount",
            "vat_percentage",
            "traffic_fines",
            "damage_fees",
            "other_charges",
            "rental_days",
            "net_total",
            "auto_renew",
            "created_by",
            "created_at",
        ]

        if obj:
            fields.insert(8, "status")

        return fields

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))

        if obj:
            readonly.extend(
                [
                    "customer",
                    "vehicle",
                    "branch",
                    "status",
                    "start_date",
                    "end_date",
                    "daily_rate",
                    "deposit_amount",
                    "vat_percentage",
                    "rental_days",
                    "damage_fees",
                    "other_charges",
                    "net_total",
                    "auto_renew",
                    "created_by",
                    "created_at",
                    "pickup_odometer",
                ]
            )
            # --- المخالفة تبقى قابلة للتعديل بعد Save ---
            # --- لكن تُقفل فقط بعد Post ---
            if obj.accounting_state == "posted" or obj.journal_entry_id:
                readonly.append("traffic_fines")

            if obj.status in ('completed', 'cancelled'):
                readonly.append('return_odometer')

        return tuple(dict.fromkeys(readonly))

        # --- علامة داخلية لتمييز سند قبض العقد الأساسي الآلي ---
    AUTO_CONTRACT_COLLECTION_NOTE = "__AUTO_CONTRACT_COLLECTION__"

    def _has_model_field(self, model_class, field_name):
        try:
            model_class._meta.get_field(field_name)
            return True
        except Exception:
            return False

    def _find_relation_field_name(self, model_class, related_model):
        for field in model_class._meta.get_fields():
            if (
                getattr(field, "is_relation", False)
                and not getattr(field, "auto_created", False)
                and getattr(field, "related_model", None) is related_model
            ):
                return field.name
        return None

    def _pick_choice_value(self, field, preferred_values):
        choices = [value for value, _label in (getattr(field, "choices", None) or [])]

        for value in preferred_values:
            if value in choices:
                return value

        return choices[0] if choices else None

    def _get_deposit_model(self):
        try:
            return apps.get_model("deposits", "Deposit")
        except LookupError:
            return None

    def _get_deposit_record(self, rental):
        Deposit = self._get_deposit_model()
        if not Deposit:
            return None

        rental_field_name = self._find_relation_field_name(Deposit, Rental)
        if not rental_field_name:
            return None

        return (
            Deposit.objects.filter(**{f"{rental_field_name}_id": rental.pk})
            .order_by("-pk")
            .first()
        )

    def _ensure_deposit_record_for_rental(self, rental):
        # --- لا ننشئ سجل تأمين إذا لم يكن هناك مبلغ تأمين أصلًا ---
        amount = Decimal(rental.deposit_amount or 0)
        if amount <= 0:
            return None

        Deposit = self._get_deposit_model()
        if not Deposit:
            raise ValidationError("Deposit model was not found in the deposits app.")

        rental_field_name = self._find_relation_field_name(Deposit, Rental)
        if not rental_field_name:
            raise ValidationError(
                "Could not detect the rental relation field on the Deposit model."
            )

        deposit_obj = self._get_deposit_record(rental)

        if deposit_obj:
            update_fields = []

            for amount_field_name in ("amount", "deposit_amount", "value"):
                if self._has_model_field(Deposit, amount_field_name):
                    current_value = Decimal(
                        getattr(deposit_obj, amount_field_name) or 0
                    )
                    if current_value != amount:
                        setattr(deposit_obj, amount_field_name, amount)
                        update_fields.append(amount_field_name)
                    break

            if update_fields:
                deposit_obj.save(update_fields=update_fields)

            return deposit_obj

        create_data = {
            rental_field_name: rental,
        }

        for amount_field_name in ("amount", "deposit_amount", "value"):
            if self._has_model_field(Deposit, amount_field_name):
                create_data[amount_field_name] = amount
                break

        if self._has_model_field(Deposit, "status"):
            status_field = Deposit._meta.get_field("status")
            pending_status = self._pick_choice_value(
                status_field,
                ["pending_collection", "pending", "draft", "active", "uncollected"],
            )
            if pending_status is not None:
                create_data["status"] = pending_status

        return Deposit.objects.create(**create_data)

    def _sync_deposit_record_after_collection(self, rental):
        # --- بعد قبض التأمين نربط القيد بسجل Deposit ونحدث حالته ---
        deposit_obj = self._ensure_deposit_record_for_rental(rental)
        if not deposit_obj or not rental.deposit_journal_entry_id:
            return deposit_obj

        Deposit = deposit_obj.__class__
        update_fields = []

        for journal_field_name in (
            "journal_entry",
            "receipt_journal_entry",
            "collection_journal_entry",
            "customer_collection_journal_entry",
        ):
            if self._has_model_field(Deposit, journal_field_name):
                current_id = getattr(deposit_obj, f"{journal_field_name}_id", None)
                if current_id != rental.deposit_journal_entry_id:
                    setattr(
                        deposit_obj, journal_field_name, rental.deposit_journal_entry
                    )
                    update_fields.append(journal_field_name)
                break

        if self._has_model_field(Deposit, "status"):
            status_field = Deposit._meta.get_field("status")
            collected_status = self._pick_choice_value(
                status_field,
                ["collected", "received", "completed", "paid", "posted"],
            )
            if (
                collected_status is not None
                and getattr(deposit_obj, "status", None) != collected_status
            ):
                setattr(deposit_obj, "status", collected_status)
                update_fields.append("status")

        if update_fields:
            deposit_obj.save(update_fields=list(dict.fromkeys(update_fields)))

        return deposit_obj

    def _get_traffic_fine_for_rental(self, rental):
        try:
            TrafficFine = apps.get_model("traffic_fines", "TrafficFine")
        except LookupError:
            return None

        rental_field_name = self._find_relation_field_name(TrafficFine, Rental)
        if not rental_field_name:
            return None

        return (
            TrafficFine.objects.filter(**{f"{rental_field_name}_id": rental.pk})
            .order_by("-pk")
            .first()
        )

    def _get_contract_receivable_amount(self, rental):
        # --- مبلغ العقد الأساسي فقط ---
        # --- أي Net Total ناقص التأمين وناقص المخالفة ---
        total = Decimal(rental.net_total or 0)
        deposit = Decimal(rental.deposit_amount or 0)
        traffic_fines = Decimal(rental.traffic_fines or 0)

        result = total - deposit - traffic_fines
        return result if result > 0 else Decimal("0.00")

    def _get_auto_contract_collection_payment(self, rental):
        return (
            Payment.objects.filter(
                rental=rental,
                notes=self.AUTO_CONTRACT_COLLECTION_NOTE,
                accounting_state="posted",
                journal_entry__isnull=False,
            )
            .order_by("-id")
            .first()
        )

    def _get_collection_amounts(self, rental):
        contract_collected = Decimal("0.00")
        deposit_collected = Decimal("0.00")
        fine_collected = Decimal("0.00")

        contract_payment = self._get_auto_contract_collection_payment(rental)
        if contract_payment:
            contract_collected = Decimal(contract_payment.amount_paid or 0)

        # --- نعتمد أولًا على سجل Deposit الحقيقي ---
        deposit_obj = self._get_deposit_record(rental)
        if deposit_obj and getattr(deposit_obj, "journal_entry_id", None):
            deposit_collected = Decimal(getattr(deposit_obj, "amount", 0) or 0)
        elif getattr(rental, "deposit_journal_entry_id", None):
            # --- توافق فقط مع بيانات قديمة من المسار السابق ---
            deposit_collected = Decimal(rental.deposit_amount or 0)

        fine = self._get_traffic_fine_for_rental(rental)
        if fine and getattr(fine, "customer_collection_journal_entry_id", None):
            fine_collected = Decimal(getattr(fine, "amount", 0) or 0)

        return {
            "contract": contract_collected,
            "deposit": deposit_collected,
            "fine": fine_collected,
            "total": contract_collected + deposit_collected + fine_collected,
        }

    def _build_collection_state_html(self, rental):
        amounts = self._get_collection_amounts(rental)

        return format_html(
            '<div id="rental-collection-state" style="display:none;" '
            'data-contract-collected="{}" '
            'data-deposit-collected="{}" '
            'data-fine-collected="{}"></div>',
            amounts["contract"],
            amounts["deposit"],
            amounts["fine"],
        )

    def _post_rental_from_admin(self, *, rental):
        from apps.accounting.services import post_rental_revenue
        from apps.deposits.services import create_deposit_from_rental

        with transaction.atomic():
            rental.refresh_from_db()

            if rental.accounting_state == "posted" or rental.journal_entry_id:
                raise ValidationError("This rental is already posted to accounting.")

            # --- Post هنا للاستحقاق فقط ---
            post_rental_revenue(rental=rental)

            # --- ننشئ سجل Deposit فقط ---
            # --- بدون قبض وبدون قيد كاش ---
            create_deposit_from_rental(rental=rental)

    def _collect_contract_and_deposit_from_admin(self, *, rental):
        from apps.accounting.services import post_payment_receipt
        from apps.deposits.services import create_deposit_from_rental, post_deposit_receipt

        with transaction.atomic():
            rental.refresh_from_db()

            if rental.accounting_state != "posted" or not rental.journal_entry_id:
                raise ValidationError("Post the rental first before collecting cash.")

            # --- أولًا: قبض مبلغ العقد الأساسي فقط ---
            contract_amount = self._get_contract_receivable_amount(rental)
            existing_contract_payment = self._get_auto_contract_collection_payment(rental)

            if contract_amount > 0 and not existing_contract_payment:
                payment = Payment(
                    rental=rental,
                    amount_paid=contract_amount,
                    method="cash",
                    status="completed",
                    payment_date=timezone.now().date(),
                    notes=self.AUTO_CONTRACT_COLLECTION_NOTE,
                )
                payment.full_clean()
                payment.save()
                post_payment_receipt(payment=payment)

            # --- ثانيًا: قبض التأمين من سجل Deposit الحقيقي ---
            deposit_obj = create_deposit_from_rental(rental=rental)
            if deposit_obj and not deposit_obj.journal_entry_id:
                post_deposit_receipt(deposit=deposit_obj)

            rental.refresh_from_db()

    def _collect_traffic_fine_from_admin(self, *, rental):
        from apps.accounting.services import post_traffic_fine_collection

        with transaction.atomic():
            rental.refresh_from_db()

            if rental.accounting_state != "posted" or not rental.journal_entry_id:
                raise ValidationError(
                    "Post the rental first before collecting the traffic fine."
                )

            fine = self._get_traffic_fine_for_rental(rental)
            if not fine:
                raise ValidationError(
                    "Traffic fine record was not found for this rental."
                )

            if getattr(fine, "customer_collection_journal_entry_id", None):
                raise ValidationError("Traffic fine is already collected.")

            update_fields = []

            if hasattr(fine, "status") and getattr(fine, "status", None) != "collected":
                fine.status = "collected"
                update_fields.append("status")

            if hasattr(fine, "collected_from_customer_date") and not getattr(
                fine, "collected_from_customer_date", None
            ):
                fine.collected_from_customer_date = timezone.now().date()
                update_fields.append("collected_from_customer_date")

            if update_fields:
                fine.save(update_fields=update_fields)

            post_traffic_fine_collection(traffic_fine=fine)

    def post_rental_button(self, obj):
        if not obj or not obj.pk:
            return "Save the rental first to enable posting."

        if obj.accounting_state == "posted" or obj.journal_entry_id:
            return mark_safe(
                '<button type="button" disabled '
                'style="background:#9ca3af; color:white; padding:10px 16px; '
                'border:none; border-radius:6px; font-weight:bold; cursor:not-allowed;">'
                'Already Posted'
                '</button>'
            )

        return mark_safe(
            '<button type="submit" name="_post_rental" value="1" '
            'style="background:#2563eb; color:white; padding:10px 16px; '
            'border:none; border-radius:6px; text-decoration:none; font-weight:bold; cursor:pointer;">'
            'Post Rental'
            '</button>'
        )

    post_rental_button.short_description = "Post Rental"

    def collect_contract_and_deposit_button(self, obj):
        hidden_state = ""
        if obj and obj.pk:
            hidden_state = self._build_collection_state_html(obj)

        if not obj or not obj.pk:
            return mark_safe(hidden_state + "Save the rental first to enable actions.")

        if obj.accounting_state != "posted" or not obj.journal_entry_id:
            return mark_safe(
                hidden_state +
                '<button type="button" disabled '
                'style="background:#9ca3af; color:white; padding:10px 16px; '
                'border:none; border-radius:6px; font-weight:bold; cursor:not-allowed;">'
                'Post Rental First'
                '</button>'
            )

        contract_amount = self._get_contract_receivable_amount(obj)
        contract_done = bool(self._get_auto_contract_collection_payment(obj)) or contract_amount <= 0
        deposit_obj = self._get_deposit_record(obj)
        deposit_done = (
            bool(getattr(deposit_obj, "journal_entry_id", None))
            or bool(obj.deposit_journal_entry_id)
            or Decimal(obj.deposit_amount or 0) <= 0
        )

        if contract_done and deposit_done:
            return mark_safe(
                hidden_state +
                '<button type="button" disabled '
                'style="background:#9ca3af; color:white; padding:10px 16px; '
                'border:none; border-radius:6px; font-weight:bold; cursor:not-allowed;">'
                'Already Collected'
                '</button>'
            )

        return mark_safe(
            hidden_state +
            '<button type="submit" name="_collect_contract_and_deposit" value="1" '
            'style="background:#059669; color:white; padding:10px 16px; '
            'border:none; border-radius:6px; font-weight:bold; cursor:pointer;">'
            'Collect Contract + Deposit'
            '</button>'
        )

    collect_contract_and_deposit_button.short_description = "Collect Contract + Deposit"

    def collect_traffic_fine_button(self, obj):
        if not obj or not obj.pk:
            return "Save the rental first to enable actions."

        if Decimal(obj.traffic_fines or 0) <= 0:
            return "No Traffic Fine."

        if obj.accounting_state != "posted" or not obj.journal_entry_id:
            return mark_safe(
                '<button type="button" disabled '
                'style="background:#9ca3af; color:white; padding:10px 16px; '
                'border:none; border-radius:6px; font-weight:bold; cursor:not-allowed;">'
                'Post Rental First'
                '</button>'
            )

        fine = self._get_traffic_fine_for_rental(obj)
        if not fine:
            return "Traffic Fine Record Not Ready."

        if getattr(fine, "customer_collection_journal_entry_id", None):
            return mark_safe(
                '<button type="button" disabled '
                'style="background:#9ca3af; color:white; padding:10px 16px; '
                'border:none; border-radius:6px; font-weight:bold; cursor:not-allowed;">'
                'Traffic Fine Collected'
                '</button>'
            )

        return mark_safe(
            '<button type="submit" name="_collect_traffic_fine" value="1" '
            'style="background:#dc2626; color:white; padding:10px 16px; '
            'border:none; border-radius:6px; font-weight:bold; cursor:pointer;">'
            'Collect Traffic Fine'
            '</button>'
        )

    collect_traffic_fine_button.short_description = "Collect Traffic Fine"

    post_rental_button.short_description = "Post Rental"

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        # --- إنشاء قاموس السياق الإضافي إذا لم يكن موجودًا ---
        extra_context = extra_context or {}

        # --- عند فتح صفحة تعديل عقد محفوظ ---
        if object_id:
            try:
                # --- جلب العقد الحالي ---
                rental = self.get_object(request, object_id)

                # --- إخفاء زر الحذف كما كان سابقًا ---
                extra_context["show_delete"] = False

                # --- جعل عنوان الصفحة يعرض رقم العقد بدل رقم الـ id ---
                if rental and rental.contract_number:
                    extra_context["title"] = f"Change Rental - {rental.contract_number}"
            except Exception:
                # --- في حال فشل الجلب نبقي السلوك الافتراضي ---
                extra_context["show_delete"] = False

        return super().changeform_view(
            request,
            object_id,
            form_url,
            extra_context=extra_context,
        )

    def has_delete_permission(self, request, obj=None):
        if obj and obj.status in ('completed', 'cancelled'):
            return False
        return super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        # --- تعبئة created_by عند الإنشاء ---
        if not obj.pk and not obj.created_by:
            obj.created_by = request.user

        # --- حفظ العقد فقط ---
        # --- مهم: لا نرحّل الـ deposit هنا ---
        super().save_model(request, obj, form, change)

    def response_change(self, request, obj):
        if "_post_rental" in request.POST:
            try:
                self._post_rental_from_admin(rental=obj)
                self.message_user(
                    request,
                    "Rental posted successfully.",
                    level=messages.SUCCESS,
                )
            except ValidationError as e:
                self.message_user(request, str(e), level=messages.ERROR)
            except Exception as e:
                self.message_user(
                    request,
                    f"Error while posting rental: {str(e)}",
                    level=messages.ERROR,
                )
            return HttpResponseRedirect(request.path)

        if "_collect_contract_and_deposit" in request.POST:
            try:
                self._collect_contract_and_deposit_from_admin(rental=obj)
                self.message_user(
                    request,
                    "Contract amount and deposit collected successfully.",
                    level=messages.SUCCESS,
                )
            except ValidationError as e:
                self.message_user(request, str(e), level=messages.ERROR)
            except Exception as e:
                self.message_user(
                    request,
                    f"Error while collecting contract/deposit: {str(e)}",
                    level=messages.ERROR,
                )
            return HttpResponseRedirect(request.path)

        if "_collect_traffic_fine" in request.POST:
            try:
                self._collect_traffic_fine_from_admin(rental=obj)
                self.message_user(
                    request,
                    "Traffic fine collected successfully.",
                    level=messages.SUCCESS,
                )
            except ValidationError as e:
                self.message_user(request, str(e), level=messages.ERROR)
            except Exception as e:
                self.message_user(
                    request,
                    f"Error while collecting traffic fine: {str(e)}",
                    level=messages.ERROR,
                )
            return HttpResponseRedirect(request.path)

        if "_return_vehicle" in request.POST:
            try:
                obj.refresh_from_db()

                if obj.status in ("completed", "cancelled"):
                    self.message_user(
                        request,
                        "Return action is not available for this rental.",
                        level=messages.ERROR,
                    )
                    return HttpResponseRedirect(request.path)

                if obj.return_odometer is None:
                    self.message_user(
                        request,
                        "Please enter return odometer before returning the vehicle.",
                        level=messages.ERROR,
                    )
                    return HttpResponseRedirect(request.path)

                if (
                    obj.pickup_odometer is not None
                    and obj.return_odometer < obj.pickup_odometer
                ):
                    self.message_user(
                        request,
                        "Return odometer cannot be less than pickup odometer.",
                        level=messages.ERROR,
                    )
                    return HttpResponseRedirect(request.path)

                obj.return_vehicle(user=request.user)
                self.message_user(
                    request,
                    "Vehicle returned successfully.",
                    level=messages.SUCCESS,
                )
            except ValidationError as e:
                self.message_user(request, str(e), level=messages.ERROR)
            except Exception as e:
                self.message_user(request, str(e), level=messages.ERROR)

            return HttpResponseRedirect(request.path)

        return super().response_change(request, obj)

    def get_customer_display(self, obj):
        # عرض العميل
        customer_name = getattr(obj.customer, 'full_name', None) or str(obj.customer)

        # محاولة إظهار الشركة إذا كانت موجودة في موديل العميل
        company_name = ''
        for attr in ['company', 'company_name', 'organization', 'company_display']:
            value = getattr(obj.customer, attr, '')
            if value:
                company_name = str(value)
                break

        creator_name = '-'
        if obj.created_by:
            creator_name = obj.created_by.get_full_name() or obj.created_by.username

        if company_name:
            return format_html(
                '<strong>{}</strong><br>'
                '<small style="color:#6b7280;">{}</small><br>'
                '<small style="color:#2563eb;">🏢 {}</small>',
                customer_name,
                company_name,
                creator_name
            )

        return format_html(
            '<strong>{}</strong><br><small style="color:#2563eb;">🏢 {}</small>',
            customer_name,
            creator_name
        )

    get_customer_display.short_description = "CUSTOMER"

    def vehicle_info(self, obj):
        # عرض السيارة بشكل آمن
        plate = getattr(obj.vehicle, 'plate_number', '-') if obj.vehicle else '-'
        vehicle_text = str(obj.vehicle) if obj.vehicle else '-'

        return format_html(
            '<strong>{}</strong><br><small style="color:#6b7280;">{}</small>',
            plate,
            vehicle_text
        )

    vehicle_info.short_description = "VEHICLE INFO"

    def _format_baghdad_datetime(self, value):
        # --- توحيد عرض أي datetime حسب توقيت بغداد المحلي ---
        if not value:
            return "-"

        # --- إذا كانت القيمة aware نحوّلها للتوقيت المحلي الحالي ---
        if timezone.is_aware(value):
            value = timezone.localtime(value)

        return value.strftime("%d-%m-%Y %H:%M")

    def pickup_time(self, obj):
        # --- عرض تاريخ بداية العقد بتوقيت بغداد الصحيح ---
        return self._format_baghdad_datetime(obj.start_date)

    pickup_time.short_description = "PICKUP TIME"

    def return_time(self, obj):
        # --- عرض تاريخ نهاية العقد المتوقع بتوقيت بغداد الصحيح ---
        return self._format_baghdad_datetime(obj.end_date)

    return_time.short_description = "RETURN TIME"

    def grand_total(self, obj):
        # عرض الإجمالي النهائي
        return format_html('<strong>$ {}</strong>', obj.net_total)

    grand_total.short_description = "GRAND TOTAL"

    def balance_due(self, obj):
        # --- الرصيد المتبقي الحقيقي حسب القبض الفعلي الجديد ---
        amounts = self._get_collection_amounts(obj)
        remaining = Decimal(obj.net_total or 0) - amounts["total"]
        color = "#e11d48" if remaining > 0 else "#059669"

        return format_html('<strong style="color:{};">$ {}</strong>', color, remaining)

    balance_due.short_description = "BALANCE DUE"

    def status_label(self, obj):
        # إذا العقد نشط لكن انتهت مدته ولم يتم إرجاع السيارة بعد
        # نعرض Active + Overdue بجانبها
        if obj.status == "active":
            base_badge = mark_safe(
                '<span style="background:#f59e0b; color:white; padding:3px 10px; '
                'border-radius:20px; font-size:10px; font-weight:bold; margin-right:6px;">Active</span>'
            )

            if obj.is_overdue:
                overdue_badge = mark_safe(
                    '<span style="background:#ef4444; color:white; padding:3px 10px; '
                    'border-radius:20px; font-size:10px; font-weight:bold;">Overdue</span>'
                )
                return mark_safe(f"{base_badge}{overdue_badge}")

            return base_badge

        if obj.status == 'completed':
            return mark_safe(
                '<span style="background:#16a34a; color:white; padding:3px 10px; '
                'border-radius:20px; font-size:10px; font-weight:bold;">Completed</span>'
            )

        if obj.status == 'cancelled':
            return mark_safe(
                '<span style="background:#6b7280; color:white; padding:3px 10px; '
                'border-radius:20px; font-size:10px; font-weight:bold;">Cancelled</span>'
            )

        return obj.get_status_display()

    status_label.short_description = "STATUS"

    def print_contract_button(self, obj):
        # --- حاشية: زر طباعة العقد ---
        if not obj or not obj.pk:
            return "Save the rental first to enable printing."

        # --- حاشية: توليد الرابط الصحيح من اسم المسار بدل كتابته يدويًا ---
        print_url = reverse("rentals:print_rental", args=[obj.id])

        return format_html(
            '<a href="{}" target="_blank" '
            'style="background:#0f172a; color:white; padding:10px 16px; '
            'border-radius:6px; text-decoration:none; font-weight:bold; display:inline-block;">'
            'Print Contract'
            '</a>',
            print_url
        )

    print_contract_button.short_description = "PRINT CONTRACT"

    def return_vehicle_button(self, obj):
        # زر إرجاع السيارة داخل صفحة العقد
        if not obj or not obj.pk:
            return "Save the rental first to enable actions."

        if obj.status in ['completed', 'cancelled']:
            return "Return action is not available for this rental."

        if obj.actual_return_date:
            return "Vehicle already returned."

        return mark_safe(
            '<button type="submit" name="_return_vehicle" value="1" '
            'style="background:#16a34a; color:white; padding:10px 16px; '
            'border:none; border-radius:6px; text-decoration:none; font-weight:bold; cursor:pointer;">'
            'Return Vehicle'
            '</button>'
        )

    return_vehicle_button.short_description = "Return Vehicle"

    # 1. أضف اسم الإجراء إلى قائمة الأكشنز (إذا كان لديك القائمة مسبقاً أضفه إليها)
    actions = ["post_selected_rentals"]

    @admin.action(description="ترحيل العقود المحددة محاسبياً (Post Rentals)")
    def post_selected_rentals(self, request, queryset):
        posted_count = 0

        for rental in queryset:
            if rental.accounting_state == "posted" or rental.journal_entry_id:
                continue

            try:
                self._post_rental_from_admin(rental=rental)
                posted_count += 1
            except Exception as e:
                self.message_user(
                    request,
                    f"❌ خطأ في ترحيل العقد {rental.id}: {str(e)}",
                    level=messages.ERROR,
                )

        if posted_count > 0:
            self.message_user(
                request,
                f"✅ تم ترحيل {posted_count} عقد بنجاح إلى شجرة الحسابات.",
                level=messages.SUCCESS,
            )

    change_form_template = "admin/rentals/rental/change_form.html"

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}

        obj = self.get_object(request, object_id)

        if obj:
            amounts = self._get_collection_amounts(obj)
            remaining_balance = Decimal(obj.net_total or 0) - amounts["total"]

            extra_context["summary_net_total"] = obj.net_total or 0
            extra_context["summary_total_paid"] = amounts["total"]
            extra_context["summary_remaining_balance"] = remaining_balance

        return super().change_view(
            request, object_id, form_url, extra_context=extra_context
        )
