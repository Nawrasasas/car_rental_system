from copy import deepcopy
from django.contrib.admin import AdminSite


class MyAdminSite(AdminSite):
    site_header = "Car Rental Enterprise Admin"
    site_title = "Car Rental Admin"
    index_title = "System Administration"

    def get_app_list(self, request, app_label=None):
        """
        ندمج invoices و payments داخل accounting في الصفحة الرئيسية للأدمن فقط
        بدون تغيير الموديلات أو قاعدة البيانات
        """
        app_list = super().get_app_list(request, app_label)
        app_list = deepcopy(app_list)

        accounting_app = None
        invoices_app = None
        payments_app = None

        for app in app_list:
            if app["app_label"] == "accounting":
                accounting_app = app
            elif app["app_label"] == "invoices":
                invoices_app = app
            elif app["app_label"] == "payments":
                payments_app = app

        if accounting_app:
            merged_models = accounting_app["models"][:]

            if invoices_app:
                merged_models.extend(invoices_app["models"])

            if payments_app:
                merged_models.extend(payments_app["models"])

            desired_order = [
                "Chart of Accounts",
                "Journal Entries",
                "Revenues",
                "Payments",
                "Expenses",
                "Invoices",
            ]

            def model_sort_key(model_dict):
                name = model_dict["name"]
                try:
                    return desired_order.index(name)
                except ValueError:
                    return len(desired_order) + 100

            merged_models.sort(key=model_sort_key)
            accounting_app["models"] = merged_models

            app_list = [
                app
                for app in app_list
                if app["app_label"] not in ["invoices", "payments"]
            ]

        return app_list


custom_admin_site = MyAdminSite(name="custom_admin")
