from django.db import migrations, models


class Migration(migrations.Migration):
    """
    تغيير اتجاه إدخال سعر الصرف من:
      rate_to_usd  = كم دولار يساوي 1 وحدة محلية (معكوس وغير بديهي)
    إلى:
      units_per_usd = كم وحدة محلية تساوي 1 دولار (طبيعي للمستخدم)

    مثال: IQD → الموظف يكتب 1500 بدل 0.000667
    """

    dependencies = [
        ("exchange_rates", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="exchangerate",
            old_name="rate_to_usd",
            new_name="units_per_usd",
        ),
        migrations.AlterField(
            model_name="exchangerate",
            name="units_per_usd",
            field=models.DecimalField(
                decimal_places=4,
                help_text=(
                    "How many units of this currency equal 1 USD. "
                    "Example: enter 1500 for IQD (meaning 1 USD = 1500 IQD)"
                ),
                max_digits=18,
                verbose_name="Units per 1 USD",
            ),
        ),
    ]
