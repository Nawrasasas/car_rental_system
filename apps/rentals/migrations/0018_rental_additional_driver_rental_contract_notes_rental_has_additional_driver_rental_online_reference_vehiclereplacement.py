# Generated migration for contract features
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('rentals', '0017_alter_rental_options'),
        ('customers', '0006_customer_driving_license_expiry_date_and_more'),
        ('vehicles', '0006_alter_vehicle_status'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ميزة 1: السائق الإضافي
        migrations.AddField(
            model_name='rental',
            name='has_additional_driver',
            field=models.BooleanField(default=False, verbose_name='Has Additional Driver'),
        ),
        migrations.AddField(
            model_name='rental',
            name='additional_driver',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='additional_driver_rentals',
                to='customers.customer',
                verbose_name='Additional Driver',
            ),
        ),
        # ميزة 2: ملاحظات العقد
        migrations.AddField(
            model_name='rental',
            name='contract_notes',
            field=models.TextField(blank=True, null=True, verbose_name='Contract Notes'),
        ),
        # ميزة 3: المرجع الخارجي
        migrations.AddField(
            model_name='rental',
            name='online_reference',
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=100,
                null=True,
                verbose_name='Online Reference',
            ),
        ),
        # ميزة 4: موديل استبدال السيارة
        migrations.CreateModel(
            name='VehicleReplacement',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('started_at', models.DateTimeField(verbose_name='Replacement Started At')),
                ('ended_at', models.DateTimeField(blank=True, null=True, verbose_name='Replacement Ended At')),
                ('reason', models.TextField(verbose_name='Reason for Replacement')),
                ('notes', models.TextField(blank=True, null=True, verbose_name='Notes')),
                ('status', models.CharField(
                    choices=[('active', 'Active'), ('completed', 'Completed')],
                    default='active',
                    max_length=20,
                    verbose_name='Status',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('ended_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='ended_replacements',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Ended By',
                )),
                ('original_vehicle', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='original_in_replacements',
                    to='vehicles.vehicle',
                    verbose_name='Original Vehicle',
                )),
                ('rental', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='replacements',
                    to='rentals.rental',
                    verbose_name='Rental',
                )),
                ('replacement_vehicle', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='used_as_replacement',
                    to='vehicles.vehicle',
                    verbose_name='Replacement Vehicle',
                )),
                ('started_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='started_replacements',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Started By',
                )),
            ],
            options={
                'verbose_name': 'Vehicle Replacement',
                'verbose_name_plural': 'Vehicle Replacements',
                'ordering': ['-created_at'],
            },
        ),
    ]
