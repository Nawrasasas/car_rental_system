from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0012_paymentrefund_delete_depositrefund'),
    ]

    operations = [
        migrations.AlterField(
            model_name='payment',
            name='method',
            field=models.CharField(
                choices=[
                    ('cash', 'Cash'),
                    ('bank_transfer', 'Bank Transfer'),
                    ('visa', 'Visa'),
                    ('mastercard', 'Mastercard'),
                    ('pos', 'POS / Card'),
                ],
                default='cash',
                max_length=20,
                verbose_name='Payment Method',
            ),
        ),
    ]
