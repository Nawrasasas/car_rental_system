from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('deposits', '0003_alter_deposit_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='deposit',
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
                verbose_name='Method',
            ),
        ),
        migrations.AlterField(
            model_name='depositrefund',
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
                verbose_name='Method',
            ),
        ),
    ]
