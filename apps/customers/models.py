from django.db import models
from django.core.exceptions import ValidationError


class Customer(models.Model):
    # خيارات نوع الزبون
    CUSTOMER_TYPE_CHOICES = (
        ('individual', 'Individual'),
        ('corporate', 'Corporate / Company'),
    )

    full_name = models.CharField(max_length=200, verbose_name="Full Name / Person in Charge")
    customer_type = models.CharField(
        max_length=20, 
        choices=CUSTOMER_TYPE_CHOICES, 
        default='individual',
        verbose_name="Customer Type"
    )

    # اسم الشركة (يملأ فقط إذا كان النوع Corporate)
    company_name = models.CharField(
        max_length=200, 
        blank=True, 
        null=True, 
        verbose_name="Company Name (e.g. Coca-Cola)"
    )

    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)
    license_number = models.CharField(
        max_length=100, verbose_name="License / ID Number"
    )

    # --- تاريخ إصدار شهادة السواقة ---
    driving_license_issue_date = models.DateField(
        null=True, blank=True, verbose_name="Driving License Issue Date"
    )

    # --- تاريخ انتهاء شهادة السواقة ---
    driving_license_expiry_date = models.DateField(
        null=True, blank=True, verbose_name="Driving License Expiry Date"
    )

    # --- بيانات جواز السفر ---
    passport_number = models.CharField(max_length=100, blank=True, null=True)

    passport_issue_date = models.DateField(
        null=True, blank=True, verbose_name="Passport Issue Date"
    )

    passport_expiry_date = models.DateField(
        null=True, blank=True, verbose_name="Passport Expiry Date"
    )

    nationality = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    def clean(self):
        # --- تحقق منطقي من تواريخ جواز السفر ---
        if self.passport_issue_date and self.passport_expiry_date:
            if self.passport_expiry_date <= self.passport_issue_date:
                raise ValidationError("Passport expiry date must be after issue date.")

        # --- تحقق منطقي من تواريخ شهادة السواقة ---
        if self.driving_license_issue_date and self.driving_license_expiry_date:
            if self.driving_license_expiry_date <= self.driving_license_issue_date:
                raise ValidationError(
                    "Driving license expiry date must be after issue date."
                )

    def __str__(self):
        # إذا كان زبون شركة، يظهر اسم الشركة بجانب اسم الشخص المسؤول
        if self.customer_type == 'corporate' and self.company_name:
            return f"{self.company_name} - ({self.full_name})"
        return self.full_name

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
