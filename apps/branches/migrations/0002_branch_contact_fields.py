from django.db import migrations, models


class Migration(migrations.Migration):
    # --- إضافة حقول التواصل للفرع لدعم صفحة الاتصال في تطبيق الموبايل ---
    dependencies = [
        ("branches", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="branch",
            name="phone",
            field=models.CharField(blank=True, default="", max_length=30, verbose_name="Phone Number"),
        ),
        migrations.AddField(
            model_name="branch",
            name="whatsapp",
            field=models.CharField(blank=True, default="", max_length=30, verbose_name="WhatsApp Number"),
        ),
        migrations.AddField(
            model_name="branch",
            name="email",
            field=models.EmailField(blank=True, default="", verbose_name="Email Address"),
        ),
        migrations.AddField(
            model_name="branch",
            name="maps_url",
            field=models.URLField(blank=True, default="", max_length=500, verbose_name="Maps URL"),
        ),
        migrations.AddField(
            model_name="branch",
            name="opening_hours",
            field=models.CharField(blank=True, default="", max_length=200, verbose_name="Opening Hours"),
        ),
        migrations.AddField(
            model_name="branch",
            name="is_main_branch",
            field=models.BooleanField(default=False, verbose_name="Is Main Branch"),
        ),
        # --- تحديث Meta تسمية النموذج ---
        migrations.AlterModelOptions(
            name="branch",
            options={"verbose_name": "Branch", "verbose_name_plural": "Branches"},
        ),
    ]
