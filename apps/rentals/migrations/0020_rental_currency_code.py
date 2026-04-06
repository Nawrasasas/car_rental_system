from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rentals", "0019_alter_rental_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="rental",
            name="currency_code",
            field=models.CharField(
                default="USD",
                max_length=3,
                verbose_name="Currency",
            ),
        ),
    ]
