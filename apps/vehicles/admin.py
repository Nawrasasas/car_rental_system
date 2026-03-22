from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import Q, Count
from apps.rentals.models import Rental
from import_export.admin import ImportExportModelAdmin
from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from apps.branches.models import Branch
from core.admin_site import custom_admin_site
from .models import Vehicle
from apps.attachments.inlines import AttachmentInline


# --- 1. Resource للاستيراد من الإكسل بأسماء الفروع ---
class VehicleResource(resources.ModelResource):
    # --- ربط حقل الفرع بالـ Branch عبر الـ id أثناء الاستيراد ---
    branch = fields.Field(
        column_name='branch',
        attribute='branch',
        widget=ForeignKeyWidget(Branch, 'id')
    )

    class Meta:
        # --- إعدادات الاستيراد والتصدير ---
        model = Vehicle
        fields = (
            'id',
            'branch',
            'plate_number',
            'brand',
            'model',
            'year',
            'vin_number',
            'current_odometer',
            'last_service_odometer',
            'service_interval',
            'daily_price',
            'status',
            'is_active',
        )
        import_id_fields = ('plate_number',)


# --- 2. Vehicle Admin المطور (الداشبورد + تقسيم البطاقة إلى 3 أقسام) ---
@admin.register(Vehicle, site=custom_admin_site)
class VehicleAdmin(ImportExportModelAdmin):
    # --- تعريف الداشبورد الداخلي ---
    resource_class = VehicleResource
    # --- استخدام نظام المرفقات العام بدل مرفقات السيارة القديمة ---
    inlines = [AttachmentInline]
    # --- الأعمدة الظاهرة في قائمة السيارات ---
    list_display = (
        'plate_number',
        'brand',
        'model',
        'vin_number',
        'status_badge',
        'status',
        'current_rental_number',
        'current_rental_branch',
        'branch',
        'daily_price',
        'current_odometer',
        'is_active',
    )

    # --- الفلاتر الجانبية ---
    list_filter = (
        'branch',
        'status',
        'brand',
        'fuel_type',
        'transmission',
        'is_active',
    )

    # --- حقول البحث ---
    search_fields = (
        'plate_number',
        'brand',
        'model',
        'vin_number',
        'engine_number',
        'insurance_policy_number',
    )

    # --- الحقول القابلة للتعديل مباشرة من قائمة السيارات ---
    list_editable = (
        'daily_price',
        'is_active',
    )

    # --- ترتيب صفحة البطاقة إلى 3 أقسام رئيسية ---
    fieldsets = (
        (
            '1) Vehicle Info',
            {
                'fields': (
                    ('plate_number', 'branch', 'status', 'is_active'),
                    ('brand', 'model', 'year'),
                    ('vin_number', 'engine_number'),
                    ('color', 'fuel_type', 'transmission', 'seats'),
                )
            }
        ),
        (
            '2) Documents & Ownership',
            {
                'fields': (
                    ('registration_expiry', 'annual_inspection_date'),
                    ('insurance_company', 'insurance_policy_number'),
                    ('insurance_expiry', 'ownership_type'),
                    ('purchase_date', 'purchase_price'),
                )
            }
        ),
        (
            '3) Rental & Operations',
            {
                'fields': (
                    ('daily_price', 'weekly_price', 'monthly_price'),
                    ('deposit_amount', 'extra_km_price'),
                    ('current_odometer', 'current_fuel_level', 'key_count'),
                    ('last_service_odometer', 'service_interval', 'next_service_odometer'),
                    ('last_service_date',),
                    ('notes',),
                )
            }
        ),
    )

    class Media:
        # --- تحميل CSS العام للسيارات + CSS العام للمعرض ---
        css = {
            "all": (
                "css/admin_custom.css",
                "css/attachment_gallery_inline.css",
            )
        }

        # --- تحميل JS العام لمعاينة المرفقات قبل الحفظ ---
        js = ("js/attachment_gallery_inline.js",)

        # --- تحسين الاستعلامات لمنع كثرة الضرب على قاعدة البيانات ---
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("rentals__branch")

    def current_rental_number(self, obj):
        # --- إظهار رقم العقد النشط الحالي للسيارة ---
        active_rental = obj.rentals.filter(status="active").order_by("-id").first()
        if active_rental:
            # نعرض رقم العقد الحقيقي بدل ID الداخلي لأن id يسبب تضارب مع رقم العقد الظاهر للمستخدم
            return active_rental.contract_number
        return "-"

    current_rental_number.short_description = 'ACTIVE RENTAL'

    def current_rental_branch(self, obj):
        # --- إظهار فرع العقد النشط الحالي ---
        active_rental = obj.rentals.filter(status='active').order_by('-id').first()
        if active_rental and active_rental.branch:
            return active_rental.branch
        return '-'

    current_rental_branch.short_description = 'RENTAL BRANCH'


    def status_badge(self, obj):
        # --- أولاً: نحدد لون شارة الحالة الأساسية حسب حالة السيارة الحالية ---
        colors = {
            "available": "#28a745",
            "rented": "#dc3545",
            "maintenance": "#ffc107",
            "service": "#17a2b8",
            "stolen": "#000000",
            "out_of_service": "#6c757d",
            "accident": "#b91c1c",
            "sold": "#1f2937",
        }

        # --- ثانيًا: نجلب اللون المناسب للحالة الحالية، وإن لم نجد حالة معروفة نستخدم لونًا رماديًا افتراضيًا ---
        color = colors.get(obj.status, "#6c757d")

        # --- ثالثًا: نبني شارة الحالة الأساسية دائمًا حتى لا تختفي Available أو Rented أو غيرها ---
        base_badge = format_html(
            '<span style="background-color: {}; color: white; padding: 5px 12px; border-radius: 15px; font-weight: bold; font-size: 11px; display: inline-block; margin-right: 6px;">{}</span>',
            color,
            obj.get_status_display(),
        )

        # --- رابعًا: إذا كانت السيارة تحتاج صيانة، نضيف شارة تنبيه بجانب الشارة الأساسية بدل أن نستبدلها ---
        if obj.needs_service:
            # --- خامسًا: نرجع الشارتين معًا: الحالة الأساسية + تنبيه الصيانة ---
            return format_html(
                '{}<span style="background-color: #ef4444; color: white; padding: 5px 12px; border-radius: 15px; font-weight: bold; font-size: 11px; display: inline-block;">⚠️ SERVICE DUE ({})</span>',
                base_badge,
                obj.km_until_service,
            )

        # --- سادسًا: إذا لم يوجد تنبيه صيانة، نرجع شارة الحالة الأساسية فقط ---
        return base_badge

    status_badge.short_description = 'Status / Alert'

    def changelist_view(self, request, extra_context=None):
        # --- تخصيص صفحة قائمة السيارات مع إحصائيات أعلى الصفحة ---
        extra_context = extra_context or {}

        # --- جلب الكويري الحالي بعد تطبيق أي فلتر من المستخدم ---
        cl = self.get_changelist_instance(request)
        queryset = cl.get_queryset(request)

        # --- حساب الإحصائيات الحالية بحسب الفلاتر المختارة ---
        stats = queryset.aggregate(
            total=Count("id"),
            available=Count("id", filter=Q(status="available")),
            rented=Count("id", filter=Q(status="rented")),
            maintenance=Count(
                "id", filter=Q(status="maintenance")
            ),  # حاشية: عدّ مستقل لحالة maintenance
            service=Count(
                "id", filter=Q(status="service")
            ),  # حاشية: عدّ مستقل لحالة service
            out_of_service=Count("id", filter=Q(status="out_of_service")),
            accident=Count("id", filter=Q(status="accident")),
            stolen=Count("id", filter=Q(status="stolen")),
        )

        # --- الاحتفاظ بباراميترات الفلترة الحالية ---
        current_params = request.GET.copy()

        # --- دالة مساعدة لإنشاء روابط الفلترة السريعة ---
        def get_filter_url(status_val):
            params = current_params.copy()
            if status_val:
                params['status__exact'] = status_val
            elif 'status__exact' in params:
                del params['status__exact']
            return f'?{params.urlencode()}'

        # --- HTML مبسط لبطاقات الإحصائيات أعلى الصفحة ---
        extra_context["dashboard_html"] = mark_safe(
            f"""
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 15px; margin-bottom: 25px;">

                <a href="{get_filter_url(None)}" style="text-decoration: none;">
                    <div style="background: white; padding: 15px; border-radius: 12px; text-align: center; border-bottom: 4px solid #6366f1; box-shadow: 0 4px 6px rgba(0,0,0,0.07); transition: transform 0.2s;" onmouseover="this.style.transform='translateY(-3px)'" onmouseout="this.style.transform='translateY(0)'">
                        <div style="font-size: 26px; font-weight: bold; color: #1e1b4b;">{stats['total']}</div>
                        <div style="font-size: 12px; color: #6366f1; font-weight: bold; text-transform: uppercase; margin-top: 5px;">Total Fleet</div>
                    </div>
                </a>

                <a href="{get_filter_url('available')}" style="text-decoration: none;">
                    <div style="background: #f0fdf4; padding: 15px; border-radius: 12px; text-align: center; border-bottom: 4px solid #22c55e; box-shadow: 0 4px 6px rgba(0,0,0,0.07); transition: transform 0.2s;" onmouseover="this.style.transform='translateY(-3px)'" onmouseout="this.style.transform='translateY(0)'">
                        <div style="font-size: 26px; font-weight: bold; color: #14532d;">{stats['available']}</div>
                        <div style="font-size: 12px; color: #16a34a; font-weight: bold; text-transform: uppercase; margin-top: 5px;">Available</div>
                    </div>
                </a>

                <a href="{get_filter_url('rented')}" style="text-decoration: none;">
                    <div style="background: #fef2f2; padding: 15px; border-radius: 12px; text-align: center; border-bottom: 4px solid #ef4444; box-shadow: 0 4px 6px rgba(0,0,0,0.07); transition: transform 0.2s;" onmouseover="this.style.transform='translateY(-3px)'" onmouseout="this.style.transform='translateY(0)'">
                        <div style="font-size: 26px; font-weight: bold; color: #7f1d1d;">{stats['rented']}</div>
                        <div style="font-size: 12px; color: #dc2626; font-weight: bold; text-transform: uppercase; margin-top: 5px;">Rented</div>
                    </div>
                </a>

                <a href="{get_filter_url('maintenance')}" style="text-decoration: none;">
                    <div style="background: #fffbeb; padding: 15px; border-radius: 12px; text-align: center; border-bottom: 4px solid #f59e0b; box-shadow: 0 4px 6px rgba(0,0,0,0.07); transition: transform 0.2s;" onmouseover="this.style.transform='translateY(-3px)'" onmouseout="this.style.transform='translateY(0)'">
                        <div style="font-size: 26px; font-weight: bold; color: #78350f;">{stats['maintenance']}</div>  <!-- حاشية: هنا يجب عرض عدد maintenance فقط لأن الرابط يفلتر maintenance فقط -->
                        <div style="font-size: 12px; color: #d97706; font-weight: bold; text-transform: uppercase; margin-top: 5px;">Maintenance</div>  <!-- حاشية: غيّرنا النص حتى يطابق الفلتر والعدد المعروض -->
                    </div>
                </a>

                <a href="{get_filter_url('service')}" style="text-decoration: none;">  <!-- حاشية: أضفنا بطاقة مستقلة لـ service لأن جمعها مع maintenance كان يسبب تضليلًا -->
                    <div style="background: #ecfeff; padding: 15px; border-radius: 12px; text-align: center; border-bottom: 4px solid #06b6d4; box-shadow: 0 4px 6px rgba(0,0,0,0.07); transition: transform 0.2s;" onmouseover="this.style.transform='translateY(-3px)'" onmouseout="this.style.transform='translateY(0)'">
                        <div style="font-size: 26px; font-weight: bold; color: #155e75;">{stats['service']}</div>  <!-- حاشية: هنا نعرض عدد service فقط -->
                        <div style="font-size: 12px; color: #0891b2; font-weight: bold; text-transform: uppercase; margin-top: 5px;">Service</div>  <!-- حاشية: النص الآن مطابق تمامًا للفلتر -->
                    </div>
                </a>

            </div>
        """
        )
        return super().changelist_view(request, extra_context=extra_context)

    def get_readonly_fields(self, request, obj=None):
        # --- إذا السيارة لديها عقد نشط نمنع تعديل الحالة ---
        if obj and obj.rentals.filter(status='active').exists():
            return ('status',)
        return ()

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(request, queryset, search_term)

        app_label = request.GET.get("app_label")
        model_name = request.GET.get("model_name")
        field_name = request.GET.get("field_name")
        object_id = request.resolver_match.kwargs.get("object_id")

        if app_label == "rentals" and model_name == "rental" and field_name == "vehicle":
            if object_id:
                try:
                    rental = Rental.objects.only("vehicle_id").get(pk=object_id)
                    queryset = queryset.filter(
                        Q(status="available") | Q(pk=rental.vehicle_id)
                    )
                except Rental.DoesNotExist:
                    queryset = queryset.filter(status="available")
            else:
                queryset = queryset.filter(status="available")

        return queryset, use_distinct
