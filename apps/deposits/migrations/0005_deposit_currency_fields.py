from django.db import migrations, models


class Migration(migrations.Migration):
    """
    إضافة حقول العملة لموديل Deposit:
    - currency_code: العملة الأصلية التي دُفع بها التأمين
    - exchange_rate_to_usd: سعر الصرف وقت الاستلام (1 وحدة محلية = X دولار)
    - amount_usd: المبلغ المعادل بالدولار بعد التحويل (محسوب تلقائيًا)
    """

    dependencies = [
        ("deposits", "0004_alter_deposit_method"),
    ]

    operations = [
        migrations.AddField(
            model_name="deposit",
            name="currency_code",
            field=models.CharField(
                choices=[
                    ("USD", "US Dollar"),
                    ("IQD", "Iraqi Dinar"),
                    ("SYP", "Syrian Pound"),
                    ("AED", "UAE Dirham"),
                ],
                default="USD",
                max_length=3,
                verbose_name="Currency",
            ),
        ),
        migrations.AddField(
            model_name="deposit",
            name="exchange_rate_to_usd",
            field=models.DecimalField(
                blank=True,
                decimal_places=6,
                max_digits=18,
                null=True,
                verbose_name="Exchange Rate To USD",
            ),
        ),
        migrations.AddField(
            model_name="deposit",
            name="amount_usd",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=18,
                null=True,
                verbose_name="Amount USD",
            ),
        ),
    ]
