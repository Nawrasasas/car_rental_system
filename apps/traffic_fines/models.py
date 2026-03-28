# PATH: apps/traffic_fines/models.py
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models


class TrafficFine(models.Model):
    STATUS_DUE = "due"
    STATUS_COLLECTED = "collected"
    STATUS_PAID_TO_GOVERNMENT = "paid_to_government"

    STATUS_CHOICES = [
        (STATUS_DUE, "Due from Customer"),
        (STATUS_COLLECTED, "Collected from Customer"),
        (STATUS_PAID_TO_GOVERNMENT, "Paid to Government"),
    ]

    # ربط أساسي بالسيارة
    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.PROTECT,
        related_name="traffic_fine_records",
        verbose_name="Vehicle",
    )

    # ربط اختياري بالعقد
    # انتبه: اخترنا related_name مختلفًا لأن Rental لديه أصلًا حقل اسمه traffic_fines
    rental = models.ForeignKey(
        "rentals.Rental",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="traffic_fine_records",
        verbose_name="Rental Contract",
    )

    violation_date = models.DateField(verbose_name="Violation Date")
    violation_type = models.CharField(max_length=150, verbose_name="Violation Type")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Amount")
    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default=STATUS_DUE,
        verbose_name="Status",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    collected_from_customer_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Collected From Customer Date",
    )
    paid_to_government_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Paid To Government Date",
    )
    customer_collection_journal_entry = models.OneToOneField(
        "accounting.JournalEntry",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="traffic_fine_customer_collection_record",
        verbose_name="Customer Collection Journal Entry",
    )

    government_payment_journal_entry = models.OneToOneField(
        "accounting.JournalEntry",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="traffic_fine_government_payment_record",
        verbose_name="Government Payment Journal Entry",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    def clean(self):
        # منع مبلغ صفري أو سالب
        if self.amount is None or self.amount <= Decimal("0.00"):
            raise ValidationError({"amount": "Amount must be greater than zero."})

        # عند اعتبارها محصلة من الزبون يجب تسجيل تاريخ التحصيل
        if (
            self.status == self.STATUS_COLLECTED
            and not self.collected_from_customer_date
        ):
            raise ValidationError(
                {
                    "collected_from_customer_date": "Collected date is required for collected fines."
                }
            )

        # عند اعتبارها مدفوعة للحكومة يجب تسجيل تاريخ الدفع
        if (
            self.status == self.STATUS_PAID_TO_GOVERNMENT
            and not self.paid_to_government_date
        ):
            raise ValidationError(
                {
                    "paid_to_government_date": "Paid date is required for government-paid fines."
                }
            )

            # --- قفل السجل بعد بدء الترحيل المحاسبي ---
        if self.pk:
            original = (
                TrafficFine.objects.filter(pk=self.pk)
                .only(
                    "vehicle_id",
                    "rental_id",
                    "violation_date",
                    "violation_type",
                    "amount",
                    "status",
                    "notes",
                    "collected_from_customer_date",
                    "paid_to_government_date",
                    "customer_collection_journal_entry_id",
                    "government_payment_journal_entry_id",
                )
                .first()
            )

            if original:
                # =========================================================
                # 1) بعد دفع المخالفة للحكومة:
                #    السجل كله يصبح مقفلاً بالكامل
                # =========================================================
                if original.government_payment_journal_entry_id:
                    locked_fields = {
                        "vehicle_id": "vehicle",
                        "rental_id": "rental contract",
                        "violation_date": "violation date",
                        "violation_type": "violation type",
                        "amount": "amount",
                        "status": "status",
                        "notes": "notes",
                        "collected_from_customer_date": "collected from customer date",
                        "paid_to_government_date": "paid to government date",
                    }

                    changed_fields = []

                    for field_name, label in locked_fields.items():
                        if getattr(original, field_name) != getattr(self, field_name):
                            changed_fields.append(label)

                    if changed_fields:
                        raise ValidationError(
                            f"This traffic fine is fully posted and cannot be edited. Locked fields: {', '.join(changed_fields)}."
                        )

                # =========================================================
                # 2) بعد تحصيلها من الزبون:
                #    لا نسمح بالرجوع أو تعديل أصل المخالفة
                #    ويسمح فقط بالخطوة التالية: Paid to Government
                # =========================================================
                elif original.customer_collection_journal_entry_id:
                    locked_fields = {
                        "vehicle_id": "vehicle",
                        "rental_id": "rental contract",
                        "violation_date": "violation date",
                        "violation_type": "violation type",
                        "amount": "amount",
                        "notes": "notes",
                        "collected_from_customer_date": "collected from customer date",
                    }

                    changed_fields = []

                    for field_name, label in locked_fields.items():
                        if getattr(original, field_name) != getattr(self, field_name):
                            changed_fields.append(label)

                    if changed_fields:
                        raise ValidationError(
                            f"This traffic fine has already been collected from the customer, so these fields are locked: {', '.join(changed_fields)}."
                        )

                    # --- منع الرجوع إلى Due بعد إنشاء قيد التحصيل ---
                    if self.status == self.STATUS_DUE:
                        raise ValidationError(
                            {
                                "status": "Cannot revert to 'Due from Customer' after posting the customer collection entry."
                            }
                        )

    def __str__(self):
        return f"{self.vehicle} - {self.violation_type} - {self.amount}"

    class Meta:
        verbose_name = "Traffic Fine"
        verbose_name_plural = "Traffic Fines"
        ordering = ["-violation_date", "-id"]
