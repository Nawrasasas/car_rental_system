from django.db import migrations


def create_pos_account(apps, schema_editor):
    Account = apps.get_model("accounting", "Account")
    # Only create if doesn't already exist
    if not Account.objects.filter(code="1130").exists():
        Account.objects.create(
            code="1130",
            name="POS / Credit Card Receivable",
            account_type="asset",
            is_active=True,
            is_postable=True,
        )


def reverse_pos_account(apps, schema_editor):
    Account = apps.get_model("accounting", "Account")
    Account.objects.filter(code="1130").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0008_journalitem_branch_journalitem_vehicle"),
    ]

    operations = [
        migrations.RunPython(create_pos_account, reverse_pos_account),
    ]
