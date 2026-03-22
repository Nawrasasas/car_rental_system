from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.db.models import Sum, F, Value, DecimalField, ExpressionWrapper, Q
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from apps.vehicles.models import Vehicle
from import_export.admin import ExportActionModelAdmin
from .models import Rental, RentalLog
from apps.attachments.inlines import AttachmentInline
from apps.payments.models import Payment
from django import forms
from core.admin_site import custom_admin_site
from django.forms.models import BaseInlineFormSet
from decimal import Decimal


class PaymentInlineFormSet(BaseInlineFormSet):
    """
    هذا الفورم يتحقق من أن مجموع جميع دفعات العقد
    لا يتجاوز صافي قيمة العقد.
    """

    def clean(self):
        super().clean()

        # إذا لم يكن هناك عقد محفوظ بعد فلا نكمل الفحص
        if not getattr(self.instance, "pk", None):
            return

        # صافي قيمة العقد
        contract_total = self.instance.net_total or Decimal("0.00")

        # سنجمع كل الدفعات الظاهرة في شاشة العقد
        total_paid = Decimal("0.00")

        for form in self.forms:
            # إذا الفورم ليس جاهزًا نتجاوزه
            if not hasattr(form, "cleaned_data"):
                continue

            # إذا السطر محذوف لا ندخله في المجموع
            if form.cleaned_data.get("DELETE", False):
                continue

            # إذا السطر فارغ نتجاوزه
            if not form.cleaned_data:
                continue

            amount = form.cleaned_data.get("amount_paid") or Decimal("0.00")

            # منع القيم السالبة
            if amount < 0:
                raise ValidationError("Payment amount cannot be negative.")

            total_paid += amount

        # إذا صار مجموع الدفعات أكبر من قيمة العقد نمنع الحفظ
        if total_paid > contract_total:
            excess = total_paid - contract_total
            raise ValidationError(
                f"Total payments ({total_paid}) cannot be greater than contract total ({contract_total}). "
                f"Exceeded amount: {excess}."
            )


class PaymentInlineForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # --- إذا كانت هذه دفعة قديمة محفوظة مسبقًا نجعلها للقراءة فقط ---
        if self.instance and self.instance.pk:
            # --- منع تعديل مبلغ الدفعة القديمة ---
            self.fields["amount_paid"].disabled = True

            # --- منع تعديل طريقة الدفع القديمة ---
            self.fields["method"].disabled = True

            # --- منع تعديل ملاحظات الدفعة القديمة ---
            self.fields["notes"].disabled = True


class PaymentInline(admin.TabularInline):
    model = Payment

    # --- ربط الـ inline بالفورم الذي يقفل الدفعات القديمة فقط ---
    form = PaymentInlineForm

    formset = PaymentInlineFormSet
    extra = 0

    fields = (
        "amount_paid",
        "method",
        "payment_date",
        "notes",
    )

    readonly_fields = ("payment_date",)

    def has_add_permission(self, request, obj=None):
        # --- لا يمكن إضافة دفعة قبل حفظ العقد أول مرة ---
        if not obj:
            return False

        # --- لا يمكن إضافة دفعة إذا العقد ملغي ---
        if obj.status == "cancelled":
            return False

        # --- لا يمكن إضافة دفعة إذا لم يعد هناك مبلغ متبقٍ ---
        if obj.remaining_amount <= 0:
            return False

        # --- بعد الحفظ نسمح بإضافة دفعات جديدة فقط ---
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # --- منع حذف أي دفعة من شاشة العقد ---
        return False


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
            passport_expiry_date = getattr(customer, "passport_expiry_date", None)
            if passport_expiry_date and passport_expiry_date <= start_date.date():
                raise forms.ValidationError(
                    "Cannot create this contract because the customer's passport is expired at or before the pickup date."
                )

        if pickup_odometer is not None and return_odometer is not None:
            if return_odometer < pickup_odometer:
                raise forms.ValidationError(
                    "Return odometer cannot be less than pickup odometer."
                )

        if (
            initial_payment_amount is not None
            and initial_payment_amount > 0
            and not initial_payment_method
        ):
            raise forms.ValidationError(
                "Please select the payment method for the initial payment."
            )

        daily_rate = cleaned_data.get("daily_rate") or Decimal("0.00")
        vat_percentage = cleaned_data.get("vat_percentage") or Decimal("0.00")
        traffic_fines = cleaned_data.get("traffic_fines") or Decimal("0.00")
        damage_fees = cleaned_data.get("damage_fees") or Decimal("0.00")
        other_charges = cleaned_data.get("other_charges") or Decimal("0.00")

        if start_date and end_date and end_date >= start_date:
            seconds = (end_date - start_date).total_seconds()
            rental_days = max(1, int(seconds // 86400))
            if seconds % 86400:
                rental_days += 1

            subtotal = Decimal(daily_rate) * Decimal(rental_days)
            vat_amount = (subtotal * Decimal(vat_percentage)) / Decimal("100")
            estimated_total = (
                subtotal + vat_amount + traffic_fines + damage_fees + other_charges
            )

            if (
                initial_payment_amount is not None
                and initial_payment_amount > estimated_total
            ):
                raise forms.ValidationError(
                    f"Initial payment cannot be greater than the contract total ({estimated_total})."
                )

        return cleaned_data


@admin.register(Rental, site=custom_admin_site)
class RentalAdmin(ExportActionModelAdmin, admin.ModelAdmin):
    form = RentalAdminForm
    autocomplete_fields = ('vehicle',)

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
        'branch',
        'auto_renew',
        'created_at',
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
        'rental_days',
        'net_total',
        'created_by',
        'created_at',
        'actual_return_date',
        'return_vehicle_button',
        'print_contract_button',
        'payment_summary_box',
    )

    # العناصر الداخلية
    inlines = [PaymentInline, AttachmentInline, ]

    # عدد العناصر في الصفحة
    list_per_page = 25

    class Media:
        css = {"all": ("css/attachment_gallery_inline.css",)}

        js = (
            "admin/js/rental_calc.js",
            "js/attachment_gallery_inline.js",
        )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        rental = form.instance
        amount = form.cleaned_data.get('initial_payment_amount')
        method = form.cleaned_data.get('initial_payment_method')
        notes = form.cleaned_data.get('initial_payment_notes')

        if not change and amount is not None and amount > 0:
            if amount > rental.net_total:
                raise ValidationError(
                    f"Initial payment cannot be greater than the contract total ({rental.net_total})."
                )

            Payment.objects.create(
                rental=rental,
                amount_paid=amount,
                method=method,
                notes=notes or '',
            )

    def get_fields(self, request, obj=None):
        fields = [
            'payment_summary_box',
            'print_contract_button',
            'return_vehicle_button',
            'customer',
            'vehicle',
            'branch',
            'pickup_odometer',
            'return_odometer',
            'start_date',
            'end_date',
            'actual_return_date',
            'daily_rate',
            'vat_percentage',
            'traffic_fines',
            'damage_fees',
            'other_charges',
            'rental_days',
            'net_total',
            'auto_renew',
            'created_by',
            'created_at',
        ]

        if not obj:
            fields.extend([
                'initial_payment_amount',
                'initial_payment_method',
                'initial_payment_notes',
            ])
        else:
            fields.insert(6, 'status')

        return fields

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))

        if obj:
            readonly.extend([
                'customer',
                'vehicle',
                'branch',
                'status',
                'start_date',
                'end_date',
                'daily_rate',
                'vat_percentage',
                'traffic_fines',
                'rental_days',
                'damage_fees',
                'other_charges',
                'net_total',
                'auto_renew',
                'created_by',
                'created_at',
                'pickup_odometer',
            ])

            if obj.status in ('completed', 'cancelled'):
                readonly.append('return_odometer')

        return tuple(dict.fromkeys(readonly))


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
        # تعبئة created_by عند الإنشاء
        if not obj.pk and not obj.created_by:
            obj.created_by = request.user

        super().save_model(request, obj, form, change)

    def response_change(self, request, obj):
        if "_return_vehicle" in request.POST:
            try:
                obj.refresh_from_db()

                if obj.status in ('completed', 'cancelled'):
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

                # تحقق إضافي ضروري
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
                self.message_user(request, f"Unexpected error: {e}", level=messages.ERROR)

            return HttpResponseRedirect(request.path)

        return super().response_change(request, obj)

    def get_queryset(self, request):
        # تحسين الاستعلامات
        qs = super().get_queryset(request)
        return qs.select_related(
            'customer',
            'vehicle',
            'branch',
            'created_by',
        ).prefetch_related(
            'payments',
            'attachments',
            'logs',
        )

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

    def pickup_time(self, obj):
        # عرض تاريخ بداية العقد
        return obj.start_date.strftime('%d-%m-%Y %H:%M') if obj.start_date else '-'

    pickup_time.short_description = "PICKUP TIME"

    def return_time(self, obj):
        # عرض تاريخ نهاية العقد المتوقع
        return obj.end_date.strftime('%d-%m-%Y %H:%M') if obj.end_date else '-'

    return_time.short_description = "RETURN TIME"

    def grand_total(self, obj):
        # عرض الإجمالي النهائي
        return format_html('<strong>$ {}</strong>', obj.net_total)

    grand_total.short_description = "GRAND TOTAL"

    def balance_due(self, obj):
        # عرض المبلغ المتبقي
        remaining = obj.remaining_amount
        color = '#e11d48' if remaining > 0 else '#059669'

        return format_html(
            '<strong style="color:{};">$ {}</strong>',
            color,
            remaining
        )

    balance_due.short_description = "BALANCE DUE"

    def payment_summary_box(self, obj):
        # --- حساب ملخص الدفع الحالي ---
        if not obj or not obj.pk:
            net_total = getattr(obj, "net_total", 0) or 0
            total_paid = 0
            remaining = net_total
        else:
            total_paid = (
                obj.payments.aggregate(
                    total=Coalesce(
                        Sum("amount_paid"),
                        Value(0),
                        output_field=DecimalField(max_digits=10, decimal_places=2),
                    )
                )["total"]
                or 0
            )

            net_total = obj.net_total or 0
            remaining = net_total - total_paid

        # --- بناء صندوق محايد لونيًا حتى لا ينكسر مع Dark Mode ---
        return format_html(
            """
            <div class="rental-payment-summary">
                <div class="rental-payment-summary__title">
                    Payment Summary
                </div>

                <div class="rental-payment-summary__row">
                    <span class="rental-payment-summary__label">Net Total</span>
                    <span class="rental-payment-summary__value">${}</span>
                </div>

                <div class="rental-payment-summary__row">
                    <span class="rental-payment-summary__label">Total Paid</span>
                    <span class="rental-payment-summary__value rental-payment-summary__value--paid">${}</span>
                </div>

                <div class="rental-payment-summary__row rental-payment-summary__row--last">
                    <span class="rental-payment-summary__label rental-payment-summary__label--strong">Remaining Balance</span>
                    <span class="rental-payment-summary__value rental-payment-summary__value--remaining">${}</span>
                </div>
            </div>
            """,
            net_total,
            total_paid,
            remaining,
        )
    payment_summary_box.short_description = " "

    def status_label(self, obj):
        # عرض حالة العقد الفعلية
        if obj.status == "active":
            return mark_safe(
                '<span style="background:#f59e0b; color:white; padding:3px 10px; '
                'border-radius:20px; font-size:10px; font-weight:bold;">Active</span>'
            )

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
        # زر طباعة العقد
        if not obj or not obj.pk:
            return "Save the rental first to enable printing."

        return format_html(
            '<a href="/rentals/{}/print/" target="_blank" '
            'style="background:#0f172a; color:white; padding:10px 16px; '
            'border-radius:6px; text-decoration:none; font-weight:bold; display:inline-block;">'
            'Print Contract'
            '</a>',
            obj.id
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


@admin.register(RentalLog, site=custom_admin_site)
class RentalLogAdmin(admin.ModelAdmin):
    # إدارة سجل العمليات
    list_display = ('id', 'rental', 'action', 'user', 'created_at')
    list_filter = ('action', 'created_at')
    search_fields = ('action', 'details', 'rental__id')
