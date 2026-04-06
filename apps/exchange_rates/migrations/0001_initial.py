from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ExchangeRate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "currency_code",
                    models.CharField(
                        choices=[
                            ("IQD", "Iraqi Dinar"),
                            ("SYP", "Syrian Pound"),
                            ("AED", "UAE Dirham"),
                        ],
                        db_index=True,
                        max_length=3,
                        verbose_name="Currency",
                    ),
                ),
                (
                    "rate_to_usd",
                    models.DecimalField(
                        decimal_places=6,
                        help_text=(
                            "How many USD is 1 unit of this currency worth. "
                            "Example: for IQD enter 0.000769 (meaning 1 USD = 1300 IQD)"
                        ),
                        max_digits=18,
                        verbose_name="Rate to USD",
                    ),
                ),
                (
                    "effective_date",
                    models.DateField(
                        db_index=True,
                        default=django.utils.timezone.localdate,
                        verbose_name="Effective Date",
                    ),
                ),
                (
                    "notes",
                    models.TextField(blank=True, verbose_name="Notes"),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Created At"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Updated At"),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="exchange_rates_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Created By",
                    ),
                ),
            ],
            options={
                "verbose_name": "Exchange Rate",
                "verbose_name_plural": "Exchange Rates",
                "ordering": ["-effective_date", "currency_code"],
            },
        ),
        migrations.AddConstraint(
            model_name="exchangerate",
            constraint=models.UniqueConstraint(
                fields=["currency_code", "effective_date"],
                name="unique_currency_per_day",
            ),
        ),
        migrations.AddIndex(
            model_name="exchangerate",
            index=models.Index(
                fields=["currency_code", "effective_date"],
                name="exchangerate_currency_date_idx",
            ),
        ),
    ]
