"""
ضعه بجانب manage.py وشغله هكذا:
    python import_customers_script.py customers_import_template.xlsx
"""

import os
import sys
import django

# إعداد Django
sys.path.insert(0, r"C:\Users\hp\Documents\car_rental_enterprise")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import pandas as pd
from datetime import date
from apps.customers.models import Customer


def parse_date(value):
    if pd.isna(value) or str(value).strip() == "":
        return None
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        return value.date()
    try:
        return pd.to_datetime(str(value).strip()).date()
    except:
        return None


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def run(filepath, dry_run=False, skip_errors=False):
    try:
        df = pd.read_excel(filepath, dtype=str, keep_default_na=False, header=0, skiprows=[1, 2])
    except FileNotFoundError:
        print(f"❌ الملف غير موجود: {filepath}")
        return

    df.columns = [
        c.strip().lower().replace(" ", "_").replace("*", "").strip("_")
        for c in df.columns
    ]
    df = df.dropna(how="all")

    created = skipped = errors = 0

    for idx, row in df.iterrows():
        row_num = idx + 2

        full_name = clean(row.get("full_name", ""))
        phone     = clean(row.get("phone", ""))
        license_n = clean(row.get("license_number", ""))
        ctype     = clean(row.get("customer_type", "individual")).lower()

        row_errors = []
        if not full_name:   row_errors.append("full_name فارغ")
        if not phone:       row_errors.append("phone فارغ")
        if not license_n:   row_errors.append("license_number فارغ")
        if ctype not in ("individual", "corporate"):
            row_errors.append(f"customer_type غير صحيح: '{ctype}'")

        p_issue   = parse_date(row.get("passport_issue_date"))
        p_expiry  = parse_date(row.get("passport_expiry_date"))
        dl_issue  = parse_date(row.get("driving_license_issue_date"))
        dl_expiry = parse_date(row.get("driving_license_expiry_date"))

        if p_issue and p_expiry and p_expiry <= p_issue:
            row_errors.append("تاريخ انتهاء الجواز قبل الإصدار")
        if dl_issue and dl_expiry and dl_expiry <= dl_issue:
            row_errors.append("تاريخ انتهاء رخصة القيادة قبل الإصدار")

        if row_errors:
            errors += 1
            print(f"⚠  صف {row_num}: {' | '.join(row_errors)}")
            if not skip_errors:
                print("تم الإيقاف. استخدم --skip-errors للمتابعة رغم الأخطاء")
                break
            continue

        if Customer.objects.filter(phone=phone).exists():
            skipped += 1
            print(f"↩  صف {row_num}: رقم الهاتف {phone} موجود مسبقاً — تم التخطي")
            continue

        if not dry_run:
            Customer.objects.create(
                full_name=full_name,
                customer_type=ctype,
                phone=phone,
                license_number=license_n,
                company_name=clean(row.get("company_name", "")) or None,
                email=clean(row.get("email", "")) or None,
                nationality=clean(row.get("nationality", "")) or None,
                address=clean(row.get("address", "")) or None,
                passport_number=clean(row.get("passport_number", "")) or None,
                passport_issue_date=p_issue,
                passport_expiry_date=p_expiry,
                driving_license_issue_date=dl_issue,
                driving_license_expiry_date=dl_expiry,
            )
        created += 1

    label = "سيتم إنشاء" if dry_run else "تم إنشاء"
    print(f"\n{'─'*40}")
    print(f"✅ {label}:   {created} زبون")
    print(f"⏭  تم تخطي:  {skipped} (مكرر)")
    print(f"❌ أخطاء:    {errors} صف")
    if dry_run:
        print("⚠  وضع التجربة — لم يُحفظ شيء في قاعدة البيانات")
    print('─'*40)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("الاستخدام:  python import_customers_script.py ملف.xlsx [--dry-run] [--skip-errors]")
        sys.exit(1)

    filepath    = sys.argv[1]
    dry_run     = "--dry-run" in sys.argv
    skip_errors = "--skip-errors" in sys.argv

    run(filepath, dry_run=dry_run, skip_errors=skip_errors)
