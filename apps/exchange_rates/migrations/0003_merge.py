from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("exchange_rates", "0002_remove_exchangerate_unique_currency_per_day_and_more"),
        ("exchange_rates", "0002_rename_rate_to_usd_to_units_per_usd"),
    ]

    operations = []
