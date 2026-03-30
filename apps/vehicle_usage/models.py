from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings
from apps.vehicles.models import Vehicle


class VehicleUsage(models.Model):
    # --- حالات سجل الاستخدام الداخلي ---
    STATUS_ACTIVE = "active"
    STATUS_RETURNED = "returned"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Active"),
        (STATUS_RETURNED, "Returned"),
        (STATUS_CANCELLED, "Cancelled"),
    )

    # --- نوع الاستخدام الداخلي ---
    PURPOSE_DELIVERY = "delivery"
    PURPOSE_MANAGER = "manager_use"
    PURPOSE_WORKSHOP = "workshop"
    PURPOSE_TRANSFER = "transfer"
    PURPOSE_OTHER = "other"

    PURPOSE_CHOICES = (
        (PURPOSE_DELIVERY, "Delivery"),
        (PURPOSE_MANAGER, "Manager Use"),
        (PURPOSE_WORKSHOP, "Workshop"),
        (PURPOSE_TRANSFER, "Transfer"),
        (PURPOSE_OTHER, "Other"),
    )

    # --- السيارة المستخدمة ---
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.PROTECT,
        related_name="vehicle_usages",
        verbose_name="Vehicle",
    )

    # --- اسم الموظف أو الشخص الذي استلم السيارة ---
    employee_name = models.CharField(
        max_length=150,
        verbose_name="Employee Name",
    )

    # --- هاتف الموظف اختياري ---
    employee_phone = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Employee Phone",
    )

    # --- نوع الاستخدام ---
    purpose = models.CharField(
        max_length=30,
        choices=PURPOSE_CHOICES,
        default=PURPOSE_OTHER,
        verbose_name="Purpose",
    )

    # --- سبب أو تفاصيل إضافية ---
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes",
    )

    # --- وقت استلام السيارة ---
    start_datetime = models.DateTimeField(
        default=timezone.now,
        verbose_name="Start Date & Time",
    )

    # --- وقت الإرجاع المتوقع ---
    expected_return_datetime = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Expected Return Date & Time",
    )

    # --- وقت الإرجاع الفعلي ---
    actual_return_datetime = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="Actual Return Date & Time",
    )

    # --- عداد الاستلام ---
    pickup_odometer = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name="Pickup Odometer",
    )

    # --- عداد الإرجاع ---
    return_odometer = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name="Return Odometer",
    )

    # --- حالة سجل الاستخدام ---
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        verbose_name="Usage Status",
    )

    # --- من أنشأ السجل ---
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="created_vehicle_usages",
        verbose_name="Created By",
    )

    # --- حقول التتبع ---
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = "Vehicle Usage"
        verbose_name_plural = "Vehicle Usage"
        ordering = ["-start_datetime", "-id"]

    def __str__(self):
        return f"{self.vehicle} | {self.employee_name} | {self.start_datetime:%Y-%m-%d %H:%M}"

    def clean(self):
        # --- منع اختيار سيارة غير متاحة عند إنشاء سجل جديد ---
        if not self.pk and self.vehicle_id and self.vehicle.status != "available":
            raise ValidationError({"vehicle": "Selected vehicle is not available."})

        # --- منع وقت إرجاع متوقع أقدم من وقت البداية ---
        if (
            self.expected_return_datetime
            and self.start_datetime
            and self.expected_return_datetime < self.start_datetime
        ):
            raise ValidationError(
                {
                    "expected_return_datetime": (
                        "Expected return time cannot be earlier than start time."
                    )
                }
            )

        # --- عند الإرجاع يجب وجود وقت إرجاع فعلي ---
        if self.status == self.STATUS_RETURNED and not self.actual_return_datetime:
            raise ValidationError(
                {
                    "actual_return_datetime": (
                        "Actual return time is required when status is Returned."
                    )
                }
            )

        # --- عند الإرجاع يجب وجود عداد إرجاع ---
        if self.status == self.STATUS_RETURNED and self.return_odometer is None:
            raise ValidationError(
                {
                    "return_odometer": (
                        "Return odometer is required when status is Returned."
                    )
                }
            )

        # --- منع أن يكون عداد الإرجاع أقل من عداد الاستلام ---
        if (
            self.pickup_odometer is not None
            and self.return_odometer is not None
            and self.return_odometer < self.pickup_odometer
        ):
            raise ValidationError(
                {
                    "return_odometer": (
                        "Return odometer cannot be less than pickup odometer."
                    )
                }
            )

        
        # --- منع وجود استخدام داخلي نشط آخر لنفس السيارة ---
        if self.vehicle_id:
            active_qs = VehicleUsage.objects.filter(
                vehicle_id=self.vehicle_id,
                status=self.STATUS_ACTIVE,
            )
            if self.pk:
                active_qs = active_qs.exclude(pk=self.pk)

            if active_qs.exists():
                raise ValidationError(
                    {
                        "vehicle": "This vehicle already has an active internal usage record."
                    }
                )

        # --- بعد الإرجاع أو الإلغاء نمنع تعديل أصل السجل الحساس ---
        if self.pk:
            original = (
                VehicleUsage.objects.filter(pk=self.pk)
                .only(
                    "vehicle_id",
                    "employee_name",
                    "start_datetime",
                    "pickup_odometer",
                    "status",
                    "actual_return_datetime",
                    "return_odometer",
                )
                .first()
            )

            if original and original.status in (
                self.STATUS_RETURNED,
                self.STATUS_CANCELLED,
            ):
                locked_fields = {
                    "vehicle_id": "vehicle",
                    "employee_name": "employee name",
                    "start_datetime": "start date & time",
                    "pickup_odometer": "pickup odometer",
                    "status": "status",
                    "actual_return_datetime": "actual return date & time",
                    "return_odometer": "return odometer",
                }

                changed_fields = []

                for field_name, label in locked_fields.items():
                    if getattr(original, field_name) != getattr(self, field_name):
                        changed_fields.append(label)

                if changed_fields:
                    raise ValidationError(
                        f"This vehicle usage record is locked because it is {original.status}. "
                        f"The following fields cannot be modified: {', '.join(changed_fields)}."
                    )

    @transaction.atomic
    def save(self, *args, **kwargs):
        # --- تحديد هل هذا سجل جديد ---
        is_new = self.pk is None

        # --- تحقق النموذج كاملًا قبل الحفظ ---
        self.full_clean()

        # --- إذا لم يدخل عداد الاستلام عند الإنشاء نأخذه من السيارة تلقائيًا ---
        if is_new and self.pickup_odometer is None and self.vehicle_id:
            self.pickup_odometer = self.vehicle.current_odometer

        super().save(*args, **kwargs)

        # --- عند الإنشاء كسجل نشط: نجعل السيارة internal_use ---
        if is_new and self.status == self.STATUS_ACTIVE:
            if self.vehicle.status != "internal_use":
                self.vehicle.status = "internal_use"
                self.vehicle.save(update_fields=["status"])

        # --- عند الإرجاع: نرجع السيارة Available ونحدث العداد ---
        if self.status == self.STATUS_RETURNED:
            update_fields = []

            if (
                self.return_odometer is not None
                and self.vehicle.current_odometer != self.return_odometer
            ):
                self.vehicle.current_odometer = self.return_odometer
                update_fields.append("current_odometer")

            if self.vehicle.status != "available":
                self.vehicle.status = "available"
                update_fields.append("status")

            if update_fields:
                self.vehicle.save(update_fields=update_fields)

        # --- عند الإلغاء: نعيد السيارة Available فقط إذا كانت ما تزال internal_use ---
        if self.status == self.STATUS_CANCELLED:
            if self.vehicle.status == "internal_use":
                self.vehicle.status = "available"
                self.vehicle.save(update_fields=["status"])

    @transaction.atomic
    def return_vehicle(self):
        # --- منع إرجاع سجل غير نشط ---
        if self.status != self.STATUS_ACTIVE:
            raise ValidationError("Only active usage records can be returned.")

        # --- يجب إدخال عداد الإرجاع أولًا ---
        if self.return_odometer is None:
            raise ValidationError(
                "Please enter return odometer before returning the vehicle."
            )

        self.actual_return_datetime = timezone.now()
        self.status = self.STATUS_RETURNED
        self.save()
