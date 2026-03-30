from django.db import migrations, models
import django.db.models.deletion


def backfill_vehicle_usage_numbers(apps, schema_editor):
    # --- نعبئ رقم الحركة للسجلات القديمة حتى لا تبقى بدون مرجع ---
    VehicleUsage = apps.get_model("vehicle_usage", "VehicleUsage")

    counters = {}

    queryset = VehicleUsage.objects.filter(usage_no__isnull=True).order_by(
        "start_datetime",
        "id",
    )

    for usage in queryset:
        base_datetime = usage.start_datetime or usage.created_at

        if base_datetime:
            period_code = base_datetime.strftime("%Y%m")
        else:
            period_code = "000000"

        next_sequence = counters.get(period_code, 0) + 1
        counters[period_code] = next_sequence

        usage.usage_no = f"VU-{period_code}-{next_sequence:04d}"

        update_fields = ["usage_no"]

        # --- فقط السجلات النشطة القديمة يمكن أخذ Source Branch الحالي لها بأمان أكبر ---
        if (
            usage.status == "active"
            and usage.vehicle_id
            and not usage.source_branch_id
            and usage.vehicle
            and usage.vehicle.branch_id
        ):
            usage.source_branch_id = usage.vehicle.branch_id
            update_fields.append("source_branch")

        usage.save(update_fields=update_fields)


def reverse_backfill_vehicle_usage_numbers(apps, schema_editor):
    # --- لا نلغي الأرقام المولدة عند الرجوع لأن السجلات قد تكون استُخدمت لاحقًا ---
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("branches", "0001_initial"),
        ("vehicle_usage", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="vehicleusage",
            name="usage_no",
            field=models.CharField(
                blank=True,
                max_length=20,
                null=True,
                unique=True,
                verbose_name="Usage No.",
            ),
        ),
        migrations.AddField(
            model_name="vehicleusage",
            name="source_branch",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="vehicle_usage_source_records",
                to="branches.branch",
                verbose_name="Source Branch",
            ),
        ),
        migrations.AddField(
            model_name="vehicleusage",
            name="destination_branch",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="vehicle_usage_destination_records",
                to="branches.branch",
                verbose_name="Destination Branch",
            ),
        ),
        migrations.AddField(
            model_name="vehicleusage",
            name="handover_by",
            field=models.CharField(
                blank=True,
                max_length=150,
                null=True,
                verbose_name="Handed Over By",
            ),
        ),
        migrations.AddField(
            model_name="vehicleusage",
            name="received_by",
            field=models.CharField(
                blank=True,
                max_length=150,
                null=True,
                verbose_name="Received By",
            ),
        ),
        migrations.RunPython(
            backfill_vehicle_usage_numbers,
            reverse_backfill_vehicle_usage_numbers,
        ),
    ]
