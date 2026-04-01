from django.db import models


class Branch(models.Model):
    name = models.CharField(max_length=100, verbose_name="Branch Name")
    location = models.CharField(max_length=200, verbose_name="Location / Address")

    # --- حقول التواصل الخاصة بكل فرع للعرض في تطبيق الموبايل ---
    phone = models.CharField(
        max_length=30,
        blank=True,
        default="",
        verbose_name="Phone Number",
    )
    whatsapp = models.CharField(
        max_length=30,
        blank=True,
        default="",
        verbose_name="WhatsApp Number",
    )
    email = models.EmailField(
        blank=True,
        default="",
        verbose_name="Email Address",
    )
    # --- رابط Google Maps أو أي خريطة للفرع ---
    maps_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        verbose_name="Maps URL",
    )
    # --- أوقات العمل مثل: الأحد - الخميس 8ص - 8م ---
    opening_hours = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name="Opening Hours",
    )
    # --- علامة الفرع الرئيسي لإظهاره أولاً ---
    is_main_branch = models.BooleanField(
        default=False,
        verbose_name="Is Main Branch",
    )

    class Meta:
        verbose_name = "Branch"
        verbose_name_plural = "Branches"

    def __str__(self):
        return self.name