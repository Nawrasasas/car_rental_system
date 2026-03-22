from django.db import models
from apps.branches.models import Branch


class Vehicle(models.Model):
    # --- خيارات حالة السيارة داخل النظام ---
    STATUS_CHOICES = (
        ('available', 'Available'),
        ('rented', 'Rented'),
        ('maintenance', 'Maintenance'),
        ('service', 'Service'),
        ('stolen', 'Stolen'),
        ('out_of_service', 'Out of Service'),
        ('accident', 'Accident'),
        ('sold', 'Sold'),
    )

    # --- خيارات نوع الوقود ---
    FUEL_TYPE_CHOICES = (
        ('gasoline', 'Gasoline'),
        ('diesel', 'Diesel'),
        ('hybrid', 'Hybrid'),
        ('electric', 'Electric'),
    )

    # --- خيارات نوع ناقل الحركة ---
    TRANSMISSION_CHOICES = (
        ('automatic', 'Automatic'),
        ('manual', 'Manual'),
    )

    # --- خيارات نوع الملكية ---
    OWNERSHIP_TYPE_CHOICES = (
        ('company', 'Company Owned'),
        ('external', 'External / Third Party'),
    )

    # --- الفرع الذي تتبع له السيارة ---
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        verbose_name='Branch / City'
    )

    # =========================
    # 1) القسم الأول: بيانات السيارة الأساسية
    # =========================

    # --- رقم اللوحة ---
    plate_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Plate Number'
    )

    # --- الماركة ---
    brand = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Brand'
    )

    # --- الموديل ---
    model = models.CharField(
        max_length=100,
        verbose_name='Model'
    )

    # --- سنة الصنع ---
    year = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Year'
    )

    # --- رقم الشاصي / VIN ---
    vin_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Chassis / VIN Number'
    )

    # --- رقم المحرك ---
    engine_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Engine Number'
    )

    # --- لون السيارة ---
    color = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Color'
    )

    # --- نوع الوقود ---
    fuel_type = models.CharField(
        max_length=20,
        choices=FUEL_TYPE_CHOICES,
        blank=True,
        null=True,
        verbose_name='Fuel Type'
    )

    # --- نوع القير ---
    transmission = models.CharField(
        max_length=20,
        choices=TRANSMISSION_CHOICES,
        blank=True,
        null=True,
        verbose_name='Transmission'
    )

    # --- عدد المقاعد ---
    seats = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        verbose_name='Seats'
    )

    # --- حالة السيارة التشغيلية ---
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='available',
        verbose_name='Vehicle Status'
    )

    # =========================
    # 2) القسم الثاني: الوثائق والشراء
    # =========================

    # --- تاريخ انتهاء التسجيل / الاستمارة ---
    registration_expiry = models.DateField(
        blank=True,
        null=True,
        verbose_name='Registration Expiry'
    )

    # --- تاريخ السنوية / الفحص السنوي ---
    annual_inspection_date = models.DateField(
        blank=True,
        null=True,
        verbose_name='Annual Inspection Date'
    )

    # --- شركة التأمين ---
    insurance_company = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name='Insurance Company'
    )

    # --- رقم وثيقة التأمين ---
    insurance_policy_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Insurance Policy Number'
    )

    # --- تاريخ انتهاء التأمين ---
    insurance_expiry = models.DateField(
        blank=True,
        null=True,
        verbose_name='Insurance Expiry'
    )

    # --- نوع ملكية السيارة ---
    ownership_type = models.CharField(
        max_length=20,
        choices=OWNERSHIP_TYPE_CHOICES,
        default='company',
        verbose_name='Ownership Type'
    )

    # --- تاريخ شراء السيارة ---
    purchase_date = models.DateField(
        blank=True,
        null=True,
        verbose_name='Purchase Date'
    )

    # --- سعر شراء السيارة ---
    purchase_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name='Purchase Price'
    )

    # =========================
    # 3) القسم الثالث: التأجير والتشغيل
    # =========================

    # --- السعر اليومي ---
    daily_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Daily Price'
    )

    # --- السعر الأسبوعي ---
    weekly_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name='Weekly Price'
    )

    # --- السعر الشهري ---
    monthly_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name='Monthly Price'
    )

    # --- مبلغ التأمين النقدي / العربون ---
    deposit_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name='Deposit Amount'
    )

    # --- سعر الكيلومتر الإضافي ---
    extra_km_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name='Extra KM Price'
    )

    # --- العداد الحالي ---
    current_odometer = models.PositiveIntegerField(
        default=0,
        verbose_name='Current Odometer (KM)'
    )

    # --- عداد آخر صيانة ---
    last_service_odometer = models.PositiveIntegerField(
        default=0,
        verbose_name='Last Service Odometer'
    )

    # --- المسافة بين كل صيانة وصيانة ---
    service_interval = models.PositiveIntegerField(
        default=5000,
        verbose_name='Service Every (KM)'
    )

    # --- تاريخ آخر صيانة ---
    last_service_date = models.DateField(
        blank=True,
        null=True,
        verbose_name='Last Service Date'
    )

    # --- عداد الصيانة القادمة ---
    next_service_odometer = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name='Next Service Odometer'
    )

    # --- مستوى الوقود الحالي ---
    current_fuel_level = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Current Fuel Level'
    )

    # --- عدد مفاتيح السيارة ---
    key_count = models.PositiveSmallIntegerField(
        default=1,
        verbose_name='Key Count'
    )

    # --- هل السيارة فعالة داخل الأسطول ---
    is_active = models.BooleanField(
        default=True,
        verbose_name='Is Active'
    )

    # --- ملاحظات عامة ---
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name='Notes'
    )

    @property
    def needs_service(self):
        # --- ترجع True إذا كانت السيارة تجاوزت المسافة المحددة للسيرفس ---
        return (self.current_odometer - self.last_service_odometer) >= self.service_interval

    @property
    def km_until_service(self):
        # --- تحسب كم كيلومتر متبقي للسيرفس القادم ---
        remaining = self.service_interval - (self.current_odometer - self.last_service_odometer)
        return max(remaining, 0)

    def __str__(self):
        # --- الاسم النصي للسيارة داخل النظام ---
        return f'{self.plate_number} | {self.brand} {self.model} - ({self.branch.name})'

    class Meta:
        # --- إعدادات إضافية للموديل ---
        verbose_name = 'Vehicle'
        verbose_name_plural = 'Vehicles'
        ordering = ['-id']


class VehicleDocument(models.Model):
    # --- ربط المستند بالسيارة ---
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.CASCADE, related_name="documents"
    )

    # --- الملف المرفوع نفسه ---
    file = models.FileField(upload_to="vehicle_docs/")

    # --- وصف اختياري للمرفق ---
    description = models.CharField(max_length=255, blank=True, null=True)

    # --- تاريخ رفع المرفق ---
    uploaded_at = models.DateTimeField(auto_now_add=True)

    @property
    def filename(self):
        # --- إرجاع اسم الملف فقط بدون المسار الكامل ---
        if not self.file:
            return ""
        return self.file.name.split("/")[-1]

    @property
    def file_url(self):
        # --- إرجاع رابط الملف إذا كان موجودًا ---
        if not self.file:
            return ""
        try:
            return self.file.url
        except Exception:
            return ""

    @property
    def is_image(self):
        # --- التحقق هل الملف المرفوع صورة كي نعرضه داخل المعرض ---
        if not self.file:
            return False

        image_extensions = (
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
            ".bmp",
            ".svg",
        )

        return self.file.name.lower().endswith(image_extensions)

    def __str__(self):
        # --- الاسم النصي للمرفق داخل النظام ---
        return f"{self.vehicle} - Document"
