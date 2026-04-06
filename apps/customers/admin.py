from django.contrib import admin
from django.shortcuts import render, redirect
from django.urls import path
from django.contrib import messages
from django.db import transaction
from .models import Customer
from core.admin_site import custom_admin_site
from apps.attachments.inlines import AttachmentInline
import pandas as pd


def parse_date(value):
    if not value or str(value).strip() in ("", "nan", "NaT"):
        return None
    if hasattr(value, "date"):
        return value.date()
    try:
        return pd.to_datetime(str(value).strip()).date()
    except Exception:
        return None


def clean(value):
    v = str(value).strip() if value is not None else ""
    return "" if v in ("nan", "NaT", "None") else v


def normalize_column_name(value):
    # توحيد أسماء الأعمدة القادمة من Excel
    # مثال:
    # full_name *  -> full_name
    # customer type -> customer_type
    return (
        str(value or "").strip().lower().replace("*", "").replace(" ", "_").strip("_")
    )


@admin.register(Customer, site=custom_admin_site)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "phone", "license_number")
    search_fields = ("full_name", "phone")
    inlines = [AttachmentInline]
    change_list_template = "admin/customers/customer/change_list.html"

    class Media:
        css = {"all": ("css/attachment_gallery_inline.css",)}
        js = ("js/attachment_gallery_inline.js",)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "import-excel/",
                self.admin_site.admin_view(self.import_excel_view),
                name="customers_import_excel",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["import_excel_url"] = "import-excel/"
        return super().changelist_view(request, extra_context=extra_context)

    def import_excel_view(self, request):
        if request.method == "POST" and request.FILES.get("excel_file"):
            excel_file = request.FILES["excel_file"]
            skip_errors = request.POST.get("skip_errors") == "on"

            try:
                # السطر 1 = أسماء الأعمدة
                # السطر 2 = ملاحظات القالب
                # السطر 3 = أول بيانات فعلية
                df = pd.read_excel(
                    excel_file,
                    dtype=str,
                    keep_default_na=False,
                    header=0,
                    skiprows=[1],
                )
            except Exception as e:
                messages.error(request, f"خطأ في قراءة الملف: {e}")
                return redirect(".")

            # تنظيف أسماء الأعمدة حتى نقبل الأعمدة التي تحتوي *
            df.columns = [normalize_column_name(c) for c in df.columns]

            # التحقق من الأعمدة المطلوبة قبل البدء
            required_columns = ["full_name", "customer_type", "phone", "license_number"]
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                messages.error(
                    request,
                    "الأعمدة المطلوبة غير موجودة أو غير مقروءة في الملف: "
                    + ", ".join(missing_columns),
                )
                return render(request, "admin/customers/import_excel.html")

            # حذف الصفوف الفارغة بالكامل
            df = df[
                ~df.apply(
                    lambda row: all(
                        str(v).strip() in ("", "nan", "NaT", "None") for v in row
                    ),
                    axis=1,
                )
            ]

            created = 0
            skipped = 0
            errors = 0
            error_msgs = []

            try:
                # عند عدم تفعيل skip_errors يكون الاستيراد all-or-nothing
                with transaction.atomic():
                    for idx, row in df.iterrows():
                        # أول صف بيانات فعلي في ملف Excel هو السطر 3
                        row_num = idx + 4

                        full_name = clean(row.get("full_name", ""))
                        phone = clean(row.get("phone", ""))
                        license_n = clean(row.get("license_number", ""))
                        ctype = clean(row.get("customer_type", "individual")).lower()

                        row_errors = []

                        if not full_name:
                            row_errors.append("full_name فارغ")
                        if not phone:
                            row_errors.append("phone فارغ")
                        if not license_n:
                            row_errors.append("license_number فارغ")
                        if ctype not in ("individual", "corporate"):
                            row_errors.append(f"customer_type غير صحيح: '{ctype}'")

                        p_issue = parse_date(row.get("passport_issue_date"))
                        p_expiry = parse_date(row.get("passport_expiry_date"))
                        dl_issue = parse_date(row.get("driving_license_issue_date"))
                        dl_expiry = parse_date(row.get("driving_license_expiry_date"))

                        if p_issue and p_expiry and p_expiry <= p_issue:
                            row_errors.append("تاريخ انتهاء الجواز قبل الإصدار")

                        if dl_issue and dl_expiry and dl_expiry <= dl_issue:
                            row_errors.append("تاريخ انتهاء رخصة القيادة قبل الإصدار")

                        if row_errors:
                            errors += 1
                            error_msgs.append(
                                f"سطر {row_num}: {' | '.join(row_errors)}"
                            )

                            if not skip_errors:
                                raise ValueError("stop")

                            continue

                        # تخطي المكرر حسب رقم الهاتف
                        if Customer.objects.filter(phone=phone).exists():
                            skipped += 1
                            continue

                        Customer.objects.create(
                            full_name=full_name,
                            customer_type=ctype,
                            phone=phone,
                            license_number=license_n,
                            company_name=clean(row.get("company_name", "")) or None,
                            email=clean(row.get("email", "")) or None,
                            nationality=clean(row.get("nationality", "")) or None,
                            address=clean(row.get("address", "")) or None,
                            passport_number=clean(row.get("passport_number", ""))
                            or None,
                            passport_issue_date=p_issue,
                            passport_expiry_date=p_expiry,
                            driving_license_issue_date=dl_issue,
                            driving_license_expiry_date=dl_expiry,
                        )
                        created += 1

            except ValueError:
                for msg in error_msgs:
                    messages.error(request, msg)

                messages.error(request, "تم إلغاء الاستيراد كاملاً — لم يُحفظ أي زبون")
                return render(request, "admin/customers/import_excel.html")

            for msg in error_msgs:
                messages.warning(request, msg)

            messages.success(
                request,
                f"✅ تم استيراد {created} زبون | ⏭ تخطي {skipped} مكرر | ❌ أخطاء {errors}",
            )
            return redirect("../")

        return render(request, "admin/customers/import_excel.html")
