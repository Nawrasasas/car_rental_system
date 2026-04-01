from django.db import migrations, models


class Migration(migrations.Migration):
    # --- إضافة حقول الموقع الجغرافي لاستعداد التتبع المباشر مستقبلاً ---
    dependencies = [
        ("vehicle_usage", "0002_vehicle_usage_transfer_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="vehicleusage",
            name="last_known_lat",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
                verbose_name="Last Known Latitude",
            ),
        ),
        migrations.AddField(
            model_name="vehicleusage",
            name="last_known_lng",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=9,
                null=True,
                verbose_name="Last Known Longitude",
            ),
        ),
        migrations.AddField(
            model_name="vehicleusage",
            name="last_location_updated_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Last Location Updated At",
            ),
        ),
    ]
