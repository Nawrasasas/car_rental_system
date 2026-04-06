from django.db import migrations


def create_iqd_cash_account(apps, schema_editor):
    Account = apps.get_model("accounting", "Account")

    # حساب النقدية الرئيسي (USD) - كود 1110
    # نجعله Header فقط إذا أردنا تجميع النقديات تحته
    # لكن نحن نبقيه postable لأن قيوده القديمة مرتبطة به
    # نُنشئ حساب الدينار العراقي كحساب مستقل بنفس المستوى

    if not Account.objects.filter(code="1115").exists():
        Account.objects.create(
            code="1115",
            name="Cash - Iraqi Dinar (IQD)",
            account_type="asset",
            is_active=True,
            is_postable=True,
        )


def reverse_iqd_cash_account(apps, schema_editor):
    Account = apps.get_model("accounting", "Account")
    Account.objects.filter(code="1115").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0009_add_pos_account"),
    ]

    operations = [
        migrations.RunPython(create_iqd_cash_account, reverse_iqd_cash_account),
    ]
