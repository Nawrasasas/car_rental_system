from datetime import timedelta
import calendar
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum, Q
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from apps.vehicles.models import Vehicle
from apps.customers.models import Customer
from apps.branches.models import Branch


class Rental(models.Model):

    # خيارات حالة العقد الأساسية فقط
    # ملاحظة: لا نحفظ "overdue" في قاعدة البيانات
    # لأنها حالة منطقية محسوبة وليست حالة تعاقدية ثابتة
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    ACCOUNTING_STATE_CHOICES = (
        ('draft', 'Draft'),
        ('posted', 'Posted'),
    )

    # العميل المرتبط بالعقد
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='rentals',
        verbose_name="Customer",
    )

    # السيارة المرتبطة بالعقد
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name='rentals',
        verbose_name="Vehicle",
    )

    # الفرع الذي تم إنشاء العقد منه
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name='rentals',
        verbose_name="Branch",
    )

    contract_number = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        null=True,
        verbose_name="Contract Number",
    )

    # حالة العقد الأساسية
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        verbose_name="Rental Status",
    )

    accounting_state = models.CharField(
        max_length=10,
        choices=ACCOUNTING_STATE_CHOICES,
        default='draft',
        verbose_name="Accounting State",
    )

    journal_entry = models.OneToOneField(
        'accounting.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='rental_record',
        verbose_name="Journal Entry",
    )

    # تاريخ بداية العقد الأصلي
    # هذا الحقل يجب ألا يتعدل بعد أول حفظ
    start_date = models.DateTimeField(verbose_name="Pickup Date")

    # تاريخ نهاية العقد الأصلي / المتوقع
    # هذا الحقل يجب ألا يتعدل بعد أول حفظ
    end_date = models.DateTimeField(verbose_name="Expected Return Date")

    # تاريخ الإرجاع الفعلي
    # يبقى فارغاً حتى يتم الضغط على زر الإرجاع أو تنفيذ الإرجاع فعلياً
    actual_return_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Actual Return Date",
    )

    pickup_odometer = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Pickup Odometer (KM)",
    )

    return_odometer = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Return Odometer (KM)",
    )

    # السعر اليومي
    daily_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Daily Rate",
    )

    # نسبة الضريبة
    vat_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.0,
        verbose_name="Tax %",
    )

    # المخالفات المرورية
    traffic_fines = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Traffic Fines",
    )

    damage_fees = models.DecimalField(
    max_digits=10,
    decimal_places=2,
    default=0,
    verbose_name="Damage Fees"
    )

    other_charges = models.DecimalField(
    max_digits=10,
    decimal_places=2,
    default=0,
    verbose_name="Other Charges"
    )

    # عدد أيام العقد المحسوبة
    rental_days = models.IntegerField(
        default=0,
        verbose_name="Rental Days",
    )

    # الإجمالي النهائي للعقد
    net_total = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name="Net Total",
    )

    # هل العقد قابل للتجديد الشهري التلقائي
    auto_renew = models.BooleanField(
        default=False,
        verbose_name="Auto Renew",
    )

    # الموظف الذي أنشأ العقد
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Created By",
    )

    # تاريخ إنشاء العقد
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At",
    )

    class Meta:
        verbose_name = "Rental"
        verbose_name_plural = "Rentals"
        ordering = ['-created_at']

    @property
    def is_overdue(self):
        # هذه الخاصية تحدد هل العقد متأخر أم لا
        # يكون متأخر إذا:
        # 1) العقد ما زال نشطاً
        # 2) لم يتم تسجيل إرجاع فعلي
        # 3) التاريخ الحالي تجاوز تاريخ الإرجاع المتوقع
        return (
            self.status == 'active'
            and self.actual_return_date is None
            and timezone.now() > self.end_date
        )

    @property
    def display_status(self):
        # هذه الخاصية مفيدة للواجهة
        # تعرض "Overdue" إذا كان العقد متأخراً
        # وإلا تعرض الحالة الأصلية المخزنة
        if self.is_overdue:
            return "Overdue"
        return self.get_status_display()

    @property
    def delay_days(self):
        # هذه الخاصية تحسب عدد أيام التأخير
        # إذا تم الإرجاع فعلياً بعد الموعد المتوقع تحسب الفرق بين actual_return_date و end_date
        # وإذا لم يتم الإرجاع بعد وكان العقد متأخراً تحسب الفرق بين الوقت الحالي و end_date
        if self.actual_return_date and self.actual_return_date > self.end_date:
            diff = self.actual_return_date - self.end_date
            return max(1, diff.days + (1 if diff.seconds > 0 else 0))

        if self.is_overdue:
            diff = timezone.now() - self.end_date
            return max(1, diff.days + (1 if diff.seconds > 0 else 0))

        return 0

    def get_paid_total(self):
        # مجموع كل الدفعات بغض النظر عن حالتها
        result = self.payments.aggregate(total=Sum('amount_paid'))
        return Decimal(result['total'] or 0)

    def get_subtotal(self):
        return (Decimal(self.rental_days or 0) * Decimal(self.daily_rate or 0)).quantize(Decimal('0.01'))

    def get_tax_amount(self):
        subtotal = self.get_subtotal()
        return (subtotal * (Decimal(self.vat_percentage or 0) / Decimal(100))).quantize(Decimal('0.01'))

    def recalculate_totals(self):
        self.rental_days = self._calculate_rental_days()
        self.net_total = self._calculate_net_total()

    @property
    def remaining_amount(self):
        total_paid = self.get_paid_total()
        return self.net_total - total_paid

    @property
    def payment_status(self):
        total_paid = self.get_paid_total()

        if total_paid >= self.net_total:
            return "Fully Paid"
        if total_paid > 0:
            return "Partial Payment"
        return "Unpaid"

    def _calculate_rental_days(self):
        if not self.start_date or not self.end_date:
            return 0

        diff = self.end_date - self.start_date
        total_seconds = int(diff.total_seconds())

        rental_days = max(1, total_seconds // 86400)

        if total_seconds % 86400:
            rental_days += 1

        return rental_days

    def _calculate_net_total(self):
        # حساب الإجمالي النهائي
        subtotal = Decimal(self.rental_days) * Decimal(self.daily_rate or 0)
        tax_amount = subtotal * (Decimal(self.vat_percentage or 0) / Decimal(100))
        return (subtotal + tax_amount + Decimal(self.traffic_fines + self.damage_fees + self.other_charges or 0)).quantize(Decimal('0.01'))

    def _has_overlapping_active_rental(self):
        # التحقق من وجود عقد نشط آخر متداخل على نفس السيارة
        if not self.vehicle_id or not self.start_date or not self.end_date:
            return False

        return Rental.objects.filter(
            vehicle_id=self.vehicle_id,
            status='active',
            start_date__lt=self.end_date,
            end_date__gt=self.start_date,
        ).exclude(pk=self.pk).exists()

    def _validate_vehicle_availability(self, locked_vehicle):
        # تحقق لحظي من حالة السيارة بعد قفل سجلها من قاعدة البيانات
        if self.status != 'active' or not locked_vehicle:
            return

        original = None
        if self.pk:
            original = Rental.objects.filter(pk=self.pk).only('status', 'vehicle_id').first()

        same_existing_active_rental = bool(
            original
            and original.status == 'active'
            and original.vehicle_id == self.vehicle_id
        )

        if not same_existing_active_rental and locked_vehicle.status != 'available':
            raise ValidationError(
    "This vehicle is currently unavailable (already rented or under maintenance). "
    "Please select another vehicle."
)

        if self._has_overlapping_active_rental():
            raise ValidationError("This vehicle already has another active rental in the selected period.")

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError(
                "Expected return date cannot be earlier than pickup date."
            )

        if self.vehicle_id and self.pickup_odometer is not None:
            current_vehicle_odometer = (
                self.vehicle.current_odometer if self.vehicle_id and hasattr(self, "vehicle") else 0
            ) or 0

            if not self.pk and self.pickup_odometer < current_vehicle_odometer:
                raise ValidationError(
                    "Pickup odometer cannot be less than the vehicle current odometer."
                )

        if self.pickup_odometer is not None and self.return_odometer is not None:
            if self.return_odometer < self.pickup_odometer:
                raise ValidationError(
                    "Return odometer cannot be less than pickup odometer."
                )

        # هذا التحقق يجب أن يعمل في الإنشاء والتعديل معًا
        if self.status == "active" and self._has_overlapping_active_rental():
            raise ValidationError(
                "This vehicle already has another active rental in the selected period."
            )

        if not self.pk:
            return

        original = (
            Rental.objects.filter(pk=self.pk)
            .only(
                "customer_id",
                "vehicle_id",
                "branch_id",
                "status",
                "start_date",
                "end_date",
                "actual_return_date",
                "daily_rate",
                "vat_percentage",
                "traffic_fines",
                "auto_renew",
                "pickup_odometer",
                "return_odometer",
            )
            .first()
        )

        if not original:
            return

        if original.start_date != self.start_date:
            raise ValidationError(
                "Pickup date cannot be changed after the rental is created."
            )

        if original.end_date != self.end_date:
            raise ValidationError(
                "Expected return date cannot be changed after the rental is created."
            )

        if original.pickup_odometer != self.pickup_odometer:
            raise ValidationError(
                "Pickup odometer cannot be changed after the rental is created."
            )

        if (
            original.status == "active"
            and self.status == "completed"
            and not self.actual_return_date
        ):
            raise ValidationError(
                "Completed rentals must be closed using the Return Vehicle action."
            )

            # قفل العقد بعد completion أو cancellation
        if original.status in ("completed", "cancelled"):
            locked_fields = {
                "customer_id": "customer",
                "vehicle_id": "vehicle",
                "branch_id": "branch",
                "status": "status",
                "actual_return_date": "actual return date",
                "daily_rate": "daily rate",
                "vat_percentage": "tax percentage",
                "traffic_fines": "traffic fines",
                "auto_renew": "auto renew",
                "pickup_odometer": "pickup odometer",
                "return_odometer": "return odometer",
            }

            changed_fields = []

            for field_name, label in locked_fields.items():
                if getattr(original, field_name) != getattr(self, field_name):
                    changed_fields.append(label)

            if changed_fields:
                raise ValidationError(
                    f"This rental is locked because it is {original.status}. "
                    f"The following fields cannot be modified: {', '.join(changed_fields)}."
                )

            original = (
                Rental.objects.filter(pk=self.pk)
                .only(
                    "customer_id",
                    "vehicle_id",
                    "branch_id",
                    "status",
                    "start_date",
                    "end_date",
                    "actual_return_date",
                    "daily_rate",
                    "vat_percentage",
                    "traffic_fines",
                    "auto_renew",
                    "pickup_odometer",
                    "return_odometer",
                )
                .first()
            )

            if not original:
                return

            # منع تعديل تاريخ البداية أو النهاية بعد أول حفظ
            if original.start_date != self.start_date:
                raise ValidationError(
                    "Pickup date cannot be changed after the rental is created."
                )

            if original.end_date != self.end_date:
                raise ValidationError(
                    "Expected return date cannot be changed after the rental is created."
                )

            # منع تغيير عداد التسليم بعد أول حفظ
            if original.pickup_odometer != self.pickup_odometer:
                raise ValidationError(
                    "Pickup odometer cannot be changed after the rental is created."
                )

            # منع إغلاق العقد يدويًا
            if (
                original.status == "active"
                and self.status == "completed"
                and not self.actual_return_date
            ):
                raise ValidationError(
                    "Completed rentals must be closed using the Return Vehicle action."
                )


    def save(self, *args, **kwargs):
        # --- إعادة حساب الأيام والإجمالي قبل الحفظ ---
        self.recalculate_totals()

        with transaction.atomic():
            # --- إذا كان رقم العقد فارغًا نولّد رقمًا جديدًا قبل الحفظ ---
            if not self.contract_number:
                # --- نأخذ السنة والشهر الحاليين بصيغة 202603 ---
                current_year_month = timezone.now().strftime("%Y%m")

                # --- نبني بادئة رقم العقد الشهرية ---
                prefix = f"RA-{current_year_month}-"

                # --- نجلب كل أرقام العقود لنفس الشهر الحالي فقط ---
                existing_numbers = (
                    Rental.objects.select_for_update()
                    .filter(contract_number__startswith=prefix)
                    .values_list("contract_number", flat=True)
                )

                # --- نحدد أعلى رقم تسلسلي موجود لهذا الشهر ---
                max_seq = 0
                for number in existing_numbers:
                    try:
                        seq = int(str(number).split("-")[-1])
                        max_seq = max(max_seq, seq)
                    except (ValueError, IndexError, AttributeError):
                        continue

                # --- توليد رقم العقد النهائي مثل RA-202603-00001 ---
                self.contract_number = f"{prefix}{str(max_seq + 1).zfill(5)}"

            # --- بعد توليد رقم العقد ننفذ التحقق الكامل ---
            self.full_clean()

            # --- قفل سجل السيارة عند وجودها ---
            locked_vehicle = None
            if self.vehicle_id:
                locked_vehicle = Vehicle.objects.select_for_update().get(pk=self.vehicle_id)

            # --- التحقق من توفر السيارة قبل الحفظ ---
            self._validate_vehicle_availability(locked_vehicle)

            # --- الحفظ الفعلي في قاعدة البيانات ---
            super().save(*args, **kwargs)

        # --- بعد الحفظ نحدّث حالة السيارة إلى rented عند الحاجة ---
        if locked_vehicle:
            if self.status == "active":
                if locked_vehicle.status != "rented":
                    locked_vehicle.status = "rented"
                    locked_vehicle.save(update_fields=["status"])

    def return_vehicle(self, user=None, save=True):
        # هذه الدالة تغلق العقد بشكل آمن داخل معاملة واحدة
        if not self.pk:
            raise ValidationError("Rental must be saved before it can be returned.")

        if not save:
            self.actual_return_date = timezone.now()
            self.status = "completed"
            return

        with transaction.atomic():
            # قفل سجل العقد والسيارة لمنع التعارض
            locked_rental = (
                Rental.objects.select_for_update().select_related("vehicle").get(pk=self.pk)
            )
            locked_vehicle = Vehicle.objects.select_for_update().get(
                pk=locked_rental.vehicle_id
            )

            # منع الإرجاع إذا العقد مكتمل مسبقًا
            if locked_rental.status == "completed":
                raise ValidationError("This rental is already completed.")

            # منع الإرجاع إذا العقد ملغي
            if locked_rental.status == "cancelled":
                raise ValidationError("Cancelled rentals cannot be returned.")

            # يجب إدخال عداد الإرجاع أولًا
            if locked_rental.return_odometer is None:
                raise ValidationError(
                    "Please enter return odometer before returning the vehicle."
                )

            # منع أن يكون عداد الإرجاع أقل من عداد التسليم
            if (
                locked_rental.pickup_odometer is not None
                and locked_rental.return_odometer < locked_rental.pickup_odometer
            ):
                raise ValidationError(
                    "Return odometer cannot be less than pickup odometer."
                )

            # تحديث العقد مباشرة بدون استدعاء save()
            actual_return_time = timezone.now()

            Rental.objects.filter(pk=locked_rental.pk).update(
                actual_return_date=actual_return_time,
                status="completed",
            )

            # تحديث نسخة الذاكرة الحالية
            locked_rental.actual_return_date = actual_return_time
            locked_rental.status = "completed"

            # تحديث عداد السيارة وحالتها
            if locked_vehicle.current_odometer != locked_rental.return_odometer:
                locked_vehicle.current_odometer = locked_rental.return_odometer
                locked_vehicle.status = "available"
                locked_vehicle.save(update_fields=["current_odometer", "status"])
            else:
                if locked_vehicle.status != "available":
                    locked_vehicle.status = "available"
                    locked_vehicle.save(update_fields=["status"])

            # تسجيل العملية في السجل
            RentalLog.objects.create(
                rental=locked_rental,
                action="Vehicle Returned",
                details=(
                    f"Vehicle returned on {locked_rental.actual_return_date:%Y-%m-%d %H:%M:%S}. "
                    f"Pickup KM: {locked_rental.pickup_odometer or 0}, "
                    f"Return KM: {locked_rental.return_odometer}."
                ),
                user=user,
            )

            # تحديث الكائن الحالي في الذاكرة بعد نجاح العملية
            self.status = locked_rental.status
            self.actual_return_date = locked_rental.actual_return_date
            self.return_odometer = locked_rental.return_odometer

    def create_monthly_renewal(self, user=None):
        # هذه الدالة تنشئ عقداً جديداً للتجديد الشهري
        # ولا تعدل تواريخ العقد الحالي لأنه أصبح ثابتاً بعد الحفظ
        if not self.auto_renew:
            raise ValidationError("Auto renew is not enabled for this rental.")

        # بداية العقد الجديد = اليوم التالي لنهاية العقد الحالي
        next_start = self.end_date + timedelta(days=1)

        # نهاية العقد الجديد = آخر يوم من نفس شهر البداية الجديدة
        # مثال:
        # end_date القديم = 2026-01-31
        # next_start = 2026-02-01
        # next_end = 2026-02-28 أو 2026-02-29
        last_day = calendar.monthrange(next_start.year, next_start.month)[1]
        next_end = next_start.replace(
                day=last_day,
                hour=self.end_date.hour,
                minute=self.end_date.minute,
                second=self.end_date.second,
                microsecond=self.end_date.microsecond,
            )

        # إنشاء عقد جديد بنفس البيانات الأساسية
        new_rental = Rental.objects.create(
                customer=self.customer,
                vehicle=self.vehicle,
                branch=self.branch,
                status='active',
                start_date=next_start,
                end_date=next_end,
                daily_rate=self.daily_rate,
                vat_percentage=self.vat_percentage,
                traffic_fines=Decimal('0.00'),
                auto_renew=self.auto_renew,
                created_by=user or self.created_by,
            )

        # تسجيل عملية التجديد في السجل للعقد الحالي
        RentalLog.objects.create(
                rental=self,
                action="Rental Renewed",
                details=(
                    f"Monthly renewal created. "
                    f"New rental #{new_rental.id} from "
                    f"{next_start:%Y-%m-%d %H:%M:%S} to "
                    f"{next_end:%Y-%m-%d %H:%M:%S}."
                ),
                user=user,
            )

        return new_rental

    def __str__(self):
        number = self.contract_number or f"Rental #{self.id}"
        customer_name = getattr(self.customer, "full_name", str(self.customer))
        return f"{number} - {customer_name} ({self.display_status})"


@receiver(post_delete, sender=Rental)
def update_vehicle_status_on_delete(sender, instance, **kwargs):
    # عند حذف العقد لا نعيد السيارة إلى available إلا إذا لم يعد هناك عقد نشط عليها
    try:
        if not instance.vehicle_id:
            return

        has_other_active_rentals = Rental.objects.filter(
                vehicle_id=instance.vehicle_id,
                status='active'
            ).exists()

        if not has_other_active_rentals:
            Vehicle.objects.filter(pk=instance.vehicle_id).update(status='available')

    except Exception:
        # نتجنب إيقاف عملية الحذف إذا حدث خطأ جانبي
        pass


@receiver(
    post_delete, sender="payments.Payment"
)  # مهم: موديل Payment موجود داخل app اسمها payments وليس rentals
def log_payment_deletion(sender, instance, **kwargs):
    # تحقق قبل الاستخدام
    if instance.rental:
        RentalLog.objects.create(
            rental=instance.rental,
            action="Payment Deleted",
            details=f"A payment of {instance.amount_paid} USD was deleted.",
            user=None,
        )


class RentalAttachment(models.Model):
    # مرفقات العقد مثل الصور أو الملفات أو المستندات
    rental = models.ForeignKey(
        Rental,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name="Rental",
    )
    file = models.FileField(
        upload_to='rentals/attachments/',
        verbose_name="File",
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Description",
    )

    class Meta:
        verbose_name = "Rental Attachment"
        verbose_name_plural = "Rental Attachments"

    def __str__(self):
        # اسم مناسب للمرفق عند العرض
        return f"Attachment #{self.id} - Rental #{self.rental_id}"


class RentalLog(models.Model):
    # سجل العمليات الخاصة بالعقد
    rental = models.ForeignKey(
        Rental,
        on_delete=models.CASCADE,
        related_name='logs',
        verbose_name="Rental",
    )

    # اسم العملية المنفذة
    action = models.CharField(
        max_length=255,
        verbose_name="Action",
    )

    # تفاصيل أو شرح إضافي للعملية
    details = models.TextField(
        verbose_name="Details",
    )

    # المستخدم / الموظف الذي قام بالعملية
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="User",
    )

    # تاريخ تنفيذ العملية
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Created At",
    )

    class Meta:
        verbose_name = "Rental Log"
        verbose_name_plural = "Rental Logs"
        ordering = ['-created_at']


    def post_to_accounting(self):
        from apps.accounting.services import post_rental_revenue

        return post_rental_revenue(rental=self.rental)  # نمرر العقد وليس السجل

    def __str__(self):
        # تمثيل نصي واضح للسجل
        return f"{self.action} - Rental #{self.rental_id}"
