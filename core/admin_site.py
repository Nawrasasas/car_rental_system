from copy import deepcopy
from django.contrib.admin import AdminSite
from django.contrib.auth.models import Group, User
from django.contrib.auth.admin import UserAdmin, GroupAdmin


class MyAdminSite(AdminSite):
    site_header = "Car Rental Enterprise Admin"
    site_title = "Car Rental Admin"
    index_title = "System Administration"

    def get_app_list(self, request, app_label=None):
        """
        ندمج invoices و payments و deposits و traffic_fines داخل accounting
        في الصفحة الرئيسية للأدمن فقط بدون تغيير الموديلات أو قاعدة البيانات
        """
        # نجلب قائمة التطبيقات الأصلية من Django Admin.
        app_list = super().get_app_list(request, app_label)

        # نأخذ نسخة مستقلة حتى لا نعدل على البنية الأصلية القادمة من Django.
        app_list = deepcopy(app_list)

        # نجهز متغيرات لالتقاط التطبيقات التي نريد دمجها داخل Accounting.
        accounting_app = None
        invoices_app = None
        payments_app = None
        deposits_app = None
        traffic_fines_app = None

        # نحدد التطبيقات المطلوبة من القائمة الحالية بحسب app_label.
        for app in app_list:
            if app["app_label"] == "accounting":
                accounting_app = app
            elif app["app_label"] == "invoices":
                invoices_app = app
            elif app["app_label"] == "payments":
                payments_app = app
            elif app["app_label"] == "deposits":
                deposits_app = app
            elif app["app_label"] == "traffic_fines":
                traffic_fines_app = app

        # إذا كان قسم Accounting موجودًا نبدأ دمج الموديلات داخله.
        if accounting_app:
            # ننسخ موديلات Accounting الحالية أولًا كما هي.
            merged_models = accounting_app["models"][:]

            # نضيف موديلات Invoices داخل Accounting.
            if invoices_app:
                merged_models.extend(invoices_app["models"])

            # نضيف موديلات Traffic Fines داخل Accounting.
            if traffic_fines_app:
                merged_models.extend(traffic_fines_app["models"])

            # نضيف موديلات Payments داخل Accounting.
            if payments_app:
                merged_models.extend(payments_app["models"])

            # نضيف موديلات Deposits داخل Accounting.
            if deposits_app:
                merged_models.extend(deposits_app["models"])

            # نحدد ترتيب الموديلات داخل قسم Accounting نفسه.
            # ترتيب العناصر داخل قسم Accounting حسب المطلوب الجديد في الواجهة.
            desired_model_order = [
                "Chart of Accounts",
                "Journal Entries",
                "Revenues",
                "Expenses",
                "Payments",
                "Invoices",
                "Deposits",
                "Deposit refunds",
                "Traffic Fines",
            ]
            # نرتب موديلات Accounting بحسب الأسماء الظاهرة في الواجهة.
            def model_sort_key(model_dict):
                name = model_dict["name"]
                try:
                    return desired_model_order.index(name)
                except ValueError:
                    return len(desired_model_order) + 100

            # نطبق الترتيب النهائي داخل قسم Accounting.
            merged_models.sort(key=model_sort_key)

            # نعيد حفظ الموديلات المدموجة داخل قسم Accounting.
            accounting_app["models"] = merged_models

            # نحذف الأقسام المنفصلة التي أصبحت مدموجة داخل Accounting
            # حتى لا يظهر Traffic Fines و Deposits و Invoices و Payments مرتين.
            app_list = [
                app
                for app in app_list
                if app["app_label"] not in ["invoices", "payments", "deposits", "traffic_fines"]
            ]

        # نحدد ترتيب الأقسام الرئيسية الظاهرة في الصفحة الرئيسية للأدمن.
        desired_app_order = [
            "Accounting",
            "Rentals",
            "Vehicles",
            "Customers",
            "Financial Reports",
            "Authentication and Authorization",
        ]

        # نرتب الأقسام الرئيسية بحسب الاسم الظاهر في الواجهة.
        def app_sort_key(app_dict):
            name = app_dict["name"]
            try:
                return desired_app_order.index(name)
            except ValueError:
                return len(desired_app_order) + 100

        # نطبق الترتيب النهائي على أقسام الصفحة الرئيسية.
        app_list.sort(key=app_sort_key)

        # نعيد القائمة النهائية بعد الدمج والترتيب.
        return app_list


custom_admin_site = MyAdminSite(name="custom_admin")

# تسجيل موديلات المستخدمين على الأدمن المخصص حتى يظهر قسم Users and Groups
#custom_admin_site.register(User, UserAdmin)
#custom_admin_site.register(Group, GroupAdmin)
custom_admin_site.disable_action("delete_selected")
