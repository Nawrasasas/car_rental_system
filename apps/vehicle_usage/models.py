from django.db import models, transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings
from apps.branches.models import Branch
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

    # --- رقم تشغيل مستقل لكل حركة Vehicle Usage للاستفادة منه لاحقًا في التقارير ---
    usage_no = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        null=True,
        verbose_name="Usage No.",
    )

    # --- السيارة المستخدمة ---
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.PROTECT,
        related_name="vehicle_usages",
        verbose_name="Vehicle",
    )

    # --- فرع الانطلاق التاريخي وقت إنشاء السجل ---
    source_branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="vehicle_usage_source_records",
        blank=True,
        null=True,
        verbose_name="Source Branch",
    )

    # --- الفرع المقابل / فرع الوصول ويستخدم فقط عند النقل بين الفروع ---
    destination_branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="vehicle_usage_destination_records",
        blank=True,
        null=True,
        verbose_name="Destination Branch",
    )

    # --- اسم الموظف أو الشخص الذي استخدم / استلم السيارة للتشغيل ---
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

    # --- اسم الشخص الذي سلّم السيارة عند الخروج ---
    handover_by = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name="Handed Over By",
    )

    # --- اسم الشخص الذي استلم السيارة عند الإغلاق / الوصول ---
    received_by = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name="Received By",
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

    # --- وقت الإرجاع الفعلي / الإغلاق الفعلي ---
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

    # --- عداد الإرجاع / التسليم ---
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
        # --- نُظهر رقم الحركة أولًا لأنه سيكون المرجع التشغيلي الأساسي ---
        usage_label = self.usage_no or "New Usage"
        return f"{usage_label} | {self.vehicle} | {self.employee_name}"

    def _get_usage_period_code(self):
        # --- نعتمد شهر/سنة وقت بداية الحركة لإنتاج رقم مرجعي منسجم مع بقية النظام ---
        base_datetime = self.start_datetime or timezone.now()

        if timezone.is_aware(base_datetime):
            base_datetime = timezone.localtime(base_datetime)

        return base_datetime.strftime("%Y%m")

    def _generate_usage_no(self):
        # --- توليد رقم مثل: VU-202603-0001 ---
        period_code = self._get_usage_period_code()
        prefix = f"VU-{period_code}-"

        last_record = (
            VehicleUsage.objects.select_for_update()
            .filter(usage_no__startswith=prefix)
            .order_by("-usage_no")
            .only("usage_no")
            .first()
        )

        next_sequence = 1

        if last_record and last_record.usage_no:
            try:
                next_sequence = int(last_record.usage_no.split("-")[-1]) + 1
            except (TypeError, ValueError):
                next_sequence = 1

        return f"{prefix}{next_sequence:04d}"

    def clean(self):
        # --- نثبت فرع الانطلاق تلقائيًا عند وجود السيارة إذا كان الحقل ما زال فارغًا ---
        if self.vehicle_id and not self.source_branch_id:
            self.source_branch = self.vehicle.branch

        # --- منع اختيار سيارة غير متاحة عند إنشاء سجل جديد ---
        if not self.pk and self.vehicle_id and self.vehicle.status != "available":
            raise ValidationError({"vehicle": "Selected vehicle is not available."})

        # --- التحقق الخاص بالنقل بين الفروع ---
        if self.purpose == self.PURPOSE_TRANSFER:
            if not self.destination_branch_id:
                raise ValidationError(
                    {
                        "destination_branch": (
                            "Destination branch is required when purpose is Transfer."
                        )
                    }
                )

            if (
                self.source_branch_id
                and self.destination_branch_id
                and self.destination_branch_id == self.source_branch_id
            ):
                raise ValidationError(
                    {
                        "destination_branch": (
                            "Destination branch cannot be the same as source branch."
                        )
                    }
                )
        else:
            # --- إذا لم تكن الحركة نقلًا فلا يجب تعبئة الفرع المقابل ---
            if self.destination_branch_id:
                raise ValidationError(
                    {
                        "destination_branch": (
                            "Destination branch is allowed only when purpose is Transfer."
                        )
                    }
                )

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

        # --- عند الإغلاق Returned يجب وجود وقت إغلاق فعلي ---
        if self.status == self.STATUS_RETURNED and not self.actual_return_datetime:
            raise ValidationError(
                {
                    "actual_return_datetime": (
                        "Actual return time is required when status is Returned."
                    )
                }
            )

        # --- عند الإغلاق Returned يجب وجود عداد إرجاع ---
        if self.status == self.STATUS_RETURNED and self.return_odometer is None:
            raise ValidationError(
                {
                    "return_odometer": (
                        "Return odometer is required when status is Returned."
                    )
                }
            )

        # --- عند إكمال النقل يجب أن يبقى الفرع المقابل موجودًا حتى لحظة الإغلاق ---
        if (
            self.status == self.STATUS_RETURNED
            and self.purpose == self.PURPOSE_TRANSFER
            and not self.destination_branch_id
        ):
            raise ValidationError(
                {
                    "destination_branch": (
                        "Destination branch is required before completing transfer."
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
                        "vehicle": (
                            "This vehicle already has an active internal usage record."
                        )
                    }
                )

        # --- عند تعديل سجل موجود نمنع العبث بالحقول التاريخية الثابتة ---
        if self.pk:
            original = (
                VehicleUsage.objects.filter(pk=self.pk)
                .only(
                    "usage_no",
                    "vehicle_id",
                    "source_branch_id",
                    "destination_branch_id",
                    "employee_name",
                    "employee_phone",
                    "purpose",
                    "handover_by",
                    "received_by",
                    "start_datetime",
                    "pickup_odometer",
                    "status",
                    "actual_return_datetime",
                    "return_odometer",
                )
                .first()
            )

            if original:
                # --- رقم الحركة يجب أن يبقى ثابتًا بعد إنشائه ---
                if original.usage_no and original.usage_no != self.usage_no:
                    raise ValidationError(
                        {"usage_no": "Usage number cannot be modified once created."}
                    )

                # --- فرع الانطلاق Snapshot تاريخي ثابت لا يُعدل ---
                if (
                    original.source_branch_id
                    and original.source_branch_id != self.source_branch_id
                ):
                    raise ValidationError(
                        {
                            "source_branch": (
                                "Source branch is a historical snapshot and cannot be modified."
                            )
                        }
                    )

                # --- بعد الإغلاق أو الإلغاء نمنع تعديل أصل السجل الحساس ---
                if original.status in (
                    self.STATUS_RETURNED,
                    self.STATUS_CANCELLED,
                ):
                    locked_fields = {
                        "vehicle_id": "vehicle",
                        "destination_branch_id": "destination branch",
                        "employee_name": "employee name",
                        "employee_phone": "employee phone",
                        "purpose": "purpose",
                        "handover_by": "handed over by",
                        "received_by": "received by",
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

        # --- نثبت فرع الانطلاق تلقائيًا عند أول إنشاء ---
        if is_new and self.vehicle_id and not self.source_branch_id:
            self.source_branch = self.vehicle.branch

        # --- إذا لم يدخل عداد الاستلام عند الإنشاء نأخذه من السيارة تلقائيًا ---
        if is_new and self.pickup_odometer is None and self.vehicle_id:
            self.pickup_odometer = self.vehicle.current_odometer

        # --- عند الإنشاء نولد رقم الحركة مع محاولة إعادة بسيطة إذا حصل تصادم نادر ---
        if is_new and not self.usage_no:
            saved_successfully = False

            for _ in range(5):
                self.usage_no = self._generate_usage_no()
                self.full_clean()

                try:
                    super().save(*args, **kwargs)
                    saved_successfully = True
                    break
                except IntegrityError:
                    # --- نعيد المحاولة برقم جديد إذا حصل تصادم نادر جدًا ---
                    self.usage_no = None

            if not saved_successfully:
                raise ValidationError(
                    {
                        "usage_no": (
                            "Could not generate a unique usage number. Please try again."
                        )
                    }
                )
        else:
            # --- تحقق النموذج كاملًا قبل الحفظ ---
            self.full_clean()
            super().save(*args, **kwargs)

        # --- عند الإنشاء كسجل نشط: نجعل السيارة internal_use ---
        if is_new and self.status == self.STATUS_ACTIVE:
            if self.vehicle.status != "internal_use":
                self.vehicle.status = "internal_use"
                self.vehicle.save(update_fields=["status"])

        # --- عند الإغلاق Returned: نحدث الفرع/العداد/الحالة حسب نوع الحركة ---
        if self.status == self.STATUS_RETURNED:
            update_fields = []

            # --- إذا كانت الحركة نقلًا بين الفروع ننقل السيارة فعليًا عند الاستلام والإغلاق ---
            if (
                self.purpose == self.PURPOSE_TRANSFER
                and self.destination_branch_id
                and self.vehicle.branch_id != self.destination_branch_id
            ):
                self.vehicle.branch_id = self.destination_branch_id
                update_fields.append("branch")

            # --- نحدث العداد النهائي عند الإغلاق ---
            if (
                self.return_odometer is not None
                and self.vehicle.current_odometer != self.return_odometer
            ):
                self.vehicle.current_odometer = self.return_odometer
                update_fields.append("current_odometer")

            # --- بعد الإغلاق تعود السيارة متاحة في الفرع النهائي ---
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
    def close_usage(self):
        # --- إغلاق عام للحركة سواء كانت استخدامًا داخليًا أو نقلًا بين الفروع ---
        if self.status != self.STATUS_ACTIVE:
            raise ValidationError("Only active usage records can be closed.")

        if self.return_odometer is None:
            raise ValidationError(
                "Please enter return odometer before closing the usage."
            )

        if self.purpose == self.PURPOSE_TRANSFER and not self.destination_branch_id:
            raise ValidationError(
                "Please select destination branch before completing transfer."
            )

        self.actual_return_datetime = timezone.now()
        self.status = self.STATUS_RETURNED
        self.save()

    def return_vehicle(self):
        # --- إبقاء هذه الدالة للتوافق مع أي استدعاءات قديمة داخل المشروع ---
        self.close_usage()
