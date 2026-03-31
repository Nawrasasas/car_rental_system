from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.admin import AdminSite
from django.db.models import Count, Sum, F, Q, DecimalField, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

from apps.branches.models import Branch
from apps.customers.models import Customer
from apps.deposits.models import Deposit
from apps.invoices.models import Invoice
from apps.payments.models import Payment
from apps.rentals.models import Rental
from apps.traffic_fines.models import TrafficFine
from apps.vehicles.models import Vehicle


class MyAdminSite(AdminSite):
    site_header = "Car Rental Enterprise Admin"
    site_title = "Car Rental Admin"
    index_title = "Operations Dashboard"
    index_template = "admin/index.html"

    def get_app_list(self, request, app_label=None):
        """
        Merge invoices, payments, deposits, and traffic fines into accounting
        on the admin homepage only, without changing database structure.
        """
        app_list = super().get_app_list(request, app_label)
        app_list = deepcopy(app_list)

        accounting_app = None
        invoices_app = None
        payments_app = None
        deposits_app = None
        traffic_fines_app = None

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

        if accounting_app:
            merged_models = accounting_app["models"][:]

            if invoices_app:
                merged_models.extend(invoices_app["models"])
            if traffic_fines_app:
                merged_models.extend(traffic_fines_app["models"])
            if payments_app:
                merged_models.extend(payments_app["models"])
            if deposits_app:
                merged_models.extend(deposits_app["models"])

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

            def model_sort_key(model_dict):
                name = model_dict["name"]
                try:
                    return desired_model_order.index(name)
                except ValueError:
                    return len(desired_model_order) + 100

            merged_models.sort(key=model_sort_key)
            accounting_app["models"] = merged_models

            app_list = [
                app
                for app in app_list
                if app["app_label"] not in ["invoices", "payments", "deposits", "traffic_fines"]
            ]

        desired_app_order = [
            "Accounting",
            "Rentals",
            "Vehicles",
            "Customers",
            "Branches",
            "Financial Reports",
            "Authentication and Authorization",
        ]

        def app_sort_key(app_dict):
            name = app_dict["name"]
            try:
                return desired_app_order.index(name)
            except ValueError:
                return len(desired_app_order) + 100

        app_list.sort(key=app_sort_key)
        return app_list

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context.update(self._build_dashboard_context(request))
        return super().index(request, extra_context=extra_context)

    def _safe_reverse(self, name):
        try:
            return reverse(name, current_app=self.name)
        except Exception:
            return "#"

    def _format_currency(self, value):
        amount = Decimal(value or 0).quantize(Decimal("0.01"))
        return f"${amount:,.2f}"

    def _format_short_datetime(self, value):
        if not value:
            return "-"
        if isinstance(value, datetime):
            if timezone.is_aware(value):
                value = timezone.localtime(value)
            return value.strftime("%d %b %Y • %H:%M")
        return str(value)

    def _make_rental_item(self, rental, badge=None, amount=None):
        customer_name = getattr(rental.customer, "full_name", "-")
        vehicle_plate = getattr(rental.vehicle, "plate_number", "-")
        branch_name = getattr(rental.branch, "name", "-")

        return {
            "title": rental.contract_number or f"Rental #{rental.pk}",
            "subtitle": f"{customer_name} • {vehicle_plate}",
            "meta": branch_name,
            "badge": badge or rental.display_status,
            "amount": amount,
            "url": self._safe_reverse("admin:rentals_rental_change").replace("/0/change/", f"/{rental.pk}/change/"),
        }

    def _make_vehicle_item(self, vehicle, badge=None, due_label=None):
        return {
            "title": vehicle.plate_number,
            "subtitle": f"{vehicle.brand or '-'} {vehicle.model or ''}".strip(),
            "meta": getattr(vehicle.branch, "name", "-"),
            "badge": badge or vehicle.get_status_display(),
            "due": due_label or "",
            "url": self._safe_reverse("admin:vehicles_vehicle_change").replace("/0/change/", f"/{vehicle.pk}/change/"),
        }

    def _make_customer_item(self, customer, badge=None, due_label=None):
        return {
            "title": customer.full_name,
            "subtitle": customer.phone or "-",
            "meta": customer.company_name or "Customer",
            "badge": badge or "Document Alert",
            "due": due_label or "",
            "url": self._safe_reverse("admin:customers_customer_change").replace("/0/change/", f"/{customer.pk}/change/"),
        }

    def _build_dashboard_context(self, request):
        now = timezone.now()
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        in_15_days = today + timedelta(days=15)
        in_30_days = today + timedelta(days=30)

        active_rentals_qs = Rental.objects.filter(
            status="active",
            actual_return_date__isnull=True,
        )
        overdue_rentals_qs = active_rentals_qs.filter(end_date__lt=now)

        service_due_qs = Vehicle.objects.filter(
            current_odometer__gte=F("last_service_odometer") + F("service_interval")
        )

        collections_today = (
            Payment.objects.filter(
                status="completed",
                payment_date=today,
            ).aggregate(total=Sum("amount_paid"))["total"]
            or Decimal("0.00")
        )

        open_deposit_exposure = (
            Deposit.objects.filter(journal_entry__isnull=False)
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        rental_paid_rows = (
            Rental.objects.annotate(
                paid_total=Coalesce(
                    Sum("payments__amount_paid"),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
            .values("id", "net_total", "paid_total")
        )

        outstanding_rental_balance = Decimal("0.00")
        for row in rental_paid_rows:
            remaining = Decimal(row["net_total"] or 0) - Decimal(row["paid_total"] or 0)
            if remaining > 0:
                outstanding_rental_balance += remaining

        vehicle_status_counts_raw = (
            Vehicle.objects.values("status")
            .annotate(total=Count("id"))
            .order_by()
        )
        vehicle_status_counts = {row["status"]: row["total"] for row in vehicle_status_counts_raw}

        overdue_items = [
            self._make_rental_item(
                rental,
                badge=f"{rental.delay_days} day(s) late",
                amount=self._format_currency(rental.remaining_amount),
            )
            for rental in overdue_rentals_qs.select_related("customer", "vehicle", "branch").order_by("end_date")[:5]
        ]

        ending_today_items = [
            self._make_rental_item(
                rental,
                badge="Due today",
                amount=self._format_currency(rental.remaining_amount),
            )
            for rental in active_rentals_qs.select_related("customer", "vehicle", "branch")
            .filter(end_date__date=today)
            .order_by("end_date")[:5]
        ]

        ending_tomorrow_items = [
            self._make_rental_item(
                rental,
                badge="Due tomorrow",
                amount=self._format_currency(rental.remaining_amount),
            )
            for rental in active_rentals_qs.select_related("customer", "vehicle", "branch")
            .filter(end_date__date=tomorrow)
            .order_by("end_date")[:5]
        ]

        outstanding_items = []
        outstanding_qs = (
            Rental.objects.select_related("customer", "vehicle", "branch")
            .annotate(
                paid_total=Coalesce(
                    Sum("payments__amount_paid"),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
            .order_by("-created_at")[:30]
        )
        for rental in outstanding_qs:
            remaining = Decimal(rental.net_total or 0) - Decimal(rental.paid_total or 0)
            if remaining > 0:
                outstanding_items.append(
                    self._make_rental_item(
                        rental,
                        badge="Balance due",
                        amount=self._format_currency(remaining),
                    )
                )
            if len(outstanding_items) >= 5:
                break

        recent_rental_items = [
            self._make_rental_item(
                rental,
                badge=rental.display_status,
                amount=self._format_currency(rental.net_total),
            )
            for rental in Rental.objects.select_related("customer", "vehicle", "branch").order_by("-created_at")[:5]
        ]

        insurance_due_items = [
            self._make_vehicle_item(
                vehicle,
                badge="Insurance Due Soon",
                due_label=vehicle.insurance_expiry.strftime("%d %b %Y") if vehicle.insurance_expiry else "",
            )
            for vehicle in Vehicle.objects.select_related("branch")
            .filter(
                insurance_expiry__isnull=False,
                insurance_expiry__gte=today,
                insurance_expiry__lte=in_15_days,
            )
            .order_by("insurance_expiry")[:5]
        ]

        insurance_expired_items = [
            self._make_vehicle_item(
                vehicle,
                badge="Insurance Expired",
                due_label=vehicle.insurance_expiry.strftime("%d %b %Y") if vehicle.insurance_expiry else "",
            )
            for vehicle in Vehicle.objects.select_related("branch")
            .filter(
                insurance_expiry__isnull=False,
                insurance_expiry__lt=today,
            )
            .order_by("insurance_expiry")[:5]
        ]

        registration_due_items = [
            self._make_vehicle_item(
                vehicle,
                badge="Registration Expiring",
                due_label=vehicle.registration_expiry.strftime("%d %b %Y") if vehicle.registration_expiry else "",
            )
            for vehicle in Vehicle.objects.select_related("branch")
            .filter(
                registration_expiry__isnull=False,
                registration_expiry__gte=today,
                registration_expiry__lte=in_30_days,
            )
            .order_by("registration_expiry")[:5]
        ]

        annual_inspection_items = [
            self._make_vehicle_item(
                vehicle,
                badge="Inspection Due",
                due_label=vehicle.annual_inspection_date.strftime("%d %b %Y") if vehicle.annual_inspection_date else "",
            )
            for vehicle in Vehicle.objects.select_related("branch")
            .filter(
                annual_inspection_date__isnull=False,
                annual_inspection_date__gte=today,
                annual_inspection_date__lte=in_30_days,
            )
            .order_by("annual_inspection_date")[:5]
        ]

        license_expiry_items = [
            self._make_customer_item(
                customer,
                badge="Driving License Expiring",
                due_label=customer.driving_license_expiry_date.strftime("%d %b %Y") if customer.driving_license_expiry_date else "",
            )
            for customer in Customer.objects.filter(
                driving_license_expiry_date__isnull=False,
                driving_license_expiry_date__gte=today,
                driving_license_expiry_date__lte=in_30_days,
            ).order_by("driving_license_expiry_date")[:5]
        ]

        passport_expiry_items = [
            self._make_customer_item(
                customer,
                badge="Passport Expiring",
                due_label=customer.passport_expiry_date.strftime("%d %b %Y") if customer.passport_expiry_date else "",
            )
            for customer in Customer.objects.filter(
                passport_expiry_date__isnull=False,
                passport_expiry_date__gte=today,
                passport_expiry_date__lte=in_30_days,
            ).order_by("passport_expiry_date")[:5]
        ]

        branch_rows = []
        for branch in Branch.objects.all().order_by("name"):
            vehicles_total = Vehicle.objects.filter(branch=branch).count()
            available_count = Vehicle.objects.filter(branch=branch, status="available").count()
            active_rentals_count = Rental.objects.filter(
                branch=branch,
                status="active",
                actual_return_date__isnull=True,
            ).count()
            collections_total = (
                Payment.objects.filter(
                    rental__branch=branch,
                    status="completed",
                    payment_date=today,
                ).aggregate(total=Sum("amount_paid"))["total"]
                or Decimal("0.00")
            )

            utilization = 0
            if vehicles_total > 0:
                utilization = round(((vehicles_total - available_count) / vehicles_total) * 100)

            branch_rows.append(
                {
                    "name": branch.name,
                    "location": branch.location,
                    "active_rentals": active_rentals_count,
                    "available_vehicles": available_count,
                    "collections_today": self._format_currency(collections_total),
                    "utilization": utilization,
                }
            )

        recent_activity = []

        for rental in Rental.objects.select_related("customer").order_by("-created_at")[:4]:
            recent_activity.append(
                {
                    "kind": "Rental",
                    "title": rental.contract_number or f"Rental #{rental.pk}",
                    "meta": getattr(rental.customer, "full_name", "-"),
                    "when": rental.created_at,
                    "url": self._safe_reverse("admin:rentals_rental_change").replace("/0/change/", f"/{rental.pk}/change/"),
                }
            )

        for payment in Payment.objects.select_related("rental").order_by("-payment_date", "-id")[:4]:
            payment_when = datetime.combine(payment.payment_date, datetime.min.time())
            payment_when = timezone.make_aware(payment_when, timezone.get_current_timezone())

            recent_activity.append(
                {
                    "kind": "Payment",
                    "title": payment.reference or f"Payment #{payment.pk}",
                    "meta": self._format_currency(payment.amount_paid),
                    "when": payment_when,
                    "url": self._safe_reverse("admin:payments_payment_change").replace("/0/change/", f"/{payment.pk}/change/"),
                }
            )

        for deposit in Deposit.objects.select_related("rental").order_by("-created_at")[:4]:
            recent_activity.append(
                {
                    "kind": "Deposit",
                    "title": deposit.reference or f"Deposit #{deposit.pk}",
                    "meta": self._format_currency(deposit.amount),
                    "when": deposit.created_at,
                    "url": self._safe_reverse("admin:deposits_deposit_change").replace("/0/change/", f"/{deposit.pk}/change/"),
                }
            )

        for invoice in Invoice.objects.order_by("-created_at")[:4]:
            recent_activity.append(
                {
                    "kind": "Invoice",
                    "title": invoice.invoice_number or f"Invoice #{invoice.pk}",
                    "meta": invoice.customer_name,
                    "when": invoice.created_at,
                    "url": self._safe_reverse("admin:invoices_invoice_change").replace("/0/change/", f"/{invoice.pk}/change/"),
                }
            )

        def _normalize_when(dt):
            if not dt:
                return timezone.now()

            if timezone.is_naive(dt):
                return timezone.make_aware(dt, timezone.get_current_timezone())

            return dt

        recent_activity.sort(key=lambda item: _normalize_when(item["when"]), reverse=True)
        recent_activity = recent_activity[:8]

        metric_cards = [
            {
                "label": "Active Rentals",
                "value": active_rentals_qs.count(),
                "tone": "blue",
                "url": f"{self._safe_reverse('admin:rentals_rental_changelist')}?rental_status=active",
            },
            {
                "label": "Overdue Rentals",
                "value": overdue_rentals_qs.count(),
                "tone": "red",
                "url": f"{self._safe_reverse('admin:rentals_rental_changelist')}?rental_status=overdue",
            },
            {
                "label": "Available Vehicles",
                "value": Vehicle.objects.filter(status="available").count(),
                "tone": "green",
                "url": f"{self._safe_reverse('admin:vehicles_vehicle_changelist')}?status__exact=available",
            },
            {
                "label": "Vehicles in Maintenance",
                "value": Vehicle.objects.filter(status="maintenance").count(),
                "tone": "amber",
                "url": f"{self._safe_reverse('admin:vehicles_vehicle_changelist')}?status__exact=maintenance",
            },
            {
                "label": "Service Due",
                "value": service_due_qs.count(),
                "tone": "violet",
                "url": self._safe_reverse("admin:vehicles_vehicle_changelist"),
            },
            {
                "label": "Collections Today",
                "value": self._format_currency(collections_today),
                "tone": "emerald",
                "url": self._safe_reverse("admin:payments_payment_changelist"),
            },
            {
                "label": "Pending Deposit Collection",
                "value": Deposit.objects.filter(journal_entry__isnull=True).count(),
                "tone": "amber",
                "url": f"{self._safe_reverse('admin:deposits_deposit_changelist')}?collection_status=pending_collection",
            },
            {
                "label": "Draft Invoices",
                "value": Invoice.objects.filter(status="draft").count(),
                "tone": "slate",
                "url": f"{self._safe_reverse('admin:invoices_invoice_changelist')}?status__exact=draft",
            },
        ]

        _veh_cl = self._safe_reverse("admin:vehicles_vehicle_changelist")
        fleet_cards = [
            {"label": "Available",     "value": vehicle_status_counts.get("available", 0),     "tone": "green",  "url": f"{_veh_cl}?status__exact=available"},
            {"label": "Rented",        "value": vehicle_status_counts.get("rented", 0),        "tone": "red",    "url": f"{_veh_cl}?status__exact=rented"},
            {"label": "Maintenance",   "value": vehicle_status_counts.get("maintenance", 0),   "tone": "amber",  "url": f"{_veh_cl}?status__exact=maintenance"},
            {"label": "Service",       "value": vehicle_status_counts.get("service", 0),       "tone": "cyan",   "url": f"{_veh_cl}?status__exact=service"},
            {"label": "Accident",      "value": vehicle_status_counts.get("accident", 0),      "tone": "rose",   "url": f"{_veh_cl}?status__exact=accident"},
            {"label": "Out of Service","value": vehicle_status_counts.get("out_of_service", 0),"tone": "slate",  "url": f"{_veh_cl}?status__exact=out_of_service"},
        ]

        financial_cards = [
            {
                "label": "Collected Today",
                "value": self._format_currency(collections_today),
                "hint": "Completed receipts recorded today",
            },
            {
                "label": "Outstanding Rental Balance",
                "value": self._format_currency(outstanding_rental_balance),
                "hint": "Open balance across rental contracts",
            },
            {
                "label": "Pending Deposit Collection",
                "value": Deposit.objects.filter(journal_entry__isnull=True).count(),
                "hint": "Deposits created but not yet collected",
            },
            {
                "label": "Open Deposit Exposure",
                "value": self._format_currency(open_deposit_exposure),
                "hint": "Collected deposits currently on record",
            },
            {
                "label": "Due Traffic Fines",
                "value": TrafficFine.objects.filter(status=TrafficFine.STATUS_DUE).count(),
                "hint": "Fines still due from customers",
            },
            {
                "label": "Draft Invoices",
                "value": Invoice.objects.filter(status="draft").count(),
                "hint": "Invoices waiting for posting",
            },
        ]

        dashboard_modules = [
            {"label": "Rentals", "url": self._safe_reverse("admin:rentals_rental_changelist"), "desc": "Contracts, returns, and operational workflow"},
            {"label": "Vehicles", "url": self._safe_reverse("admin:vehicles_vehicle_changelist"), "desc": "Fleet status, pricing, and compliance"},
            {"label": "Customers", "url": self._safe_reverse("admin:customers_customer_changelist"), "desc": "Profiles, documents, and contact details"},
            {"label": "Payments", "url": self._safe_reverse("admin:payments_payment_changelist"), "desc": "Receipts, collections, and accounting state"},
            {"label": "Deposits", "url": self._safe_reverse("admin:deposits_deposit_changelist"), "desc": "Collection and refund follow-up"},
            {"label": "Traffic Fines", "url": self._safe_reverse("admin:traffic_fines_trafficfine_changelist"), "desc": "Customer collection and settlement tracking"},
            {"label": "Invoices", "url": self._safe_reverse("admin:invoices_invoice_changelist"), "desc": "Draft, posted, and reversed invoices"},
            {"label": "Reports", "url": self._safe_reverse("admin:reports_salesreport_changelist"), "desc": "Sales and financial reporting"},
        ]

        quick_actions = [
            {"label": "Create Rental", "url": self._safe_reverse("admin:rentals_rental_add"), "variant": "primary"},
            {"label": "Collect Payment", "url": self._safe_reverse("admin:payments_payment_add"), "variant": "secondary"},
            {"label": "Return Vehicle", "url": f"{self._safe_reverse('admin:rentals_rental_changelist')}?rental_status=active", "variant": "ghost"},
        ]

        return {
            "dashboard_generated_at": timezone.localtime(now).strftime("%d %b %Y • %H:%M"),
            "dashboard_scope_label": "All Branches",
            "dashboard_quick_actions": quick_actions,
            "dashboard_metric_cards": metric_cards,
            "dashboard_rental_sections": [
                {"title": "Overdue Contracts", "items": overdue_items, "empty": "No overdue contracts."},
                {"title": "Ending Today", "items": ending_today_items, "empty": "No contracts ending today."},
                {"title": "Ending Tomorrow", "items": ending_tomorrow_items, "empty": "No contracts ending tomorrow."},
                {"title": "Outstanding Balance", "items": outstanding_items, "empty": "No open balances."},
                {"title": "Recently Created", "items": recent_rental_items, "empty": "No recent rentals."},
            ],
            "dashboard_rental_status": [
                {"label": "Active", "value": active_rentals_qs.count(), "tone": "blue"},
                {"label": "Completed", "value": Rental.objects.filter(status="completed").count(), "tone": "green"},
                {"label": "Cancelled", "value": Rental.objects.filter(status="cancelled").count(), "tone": "slate"},
                {"label": "Overdue", "value": overdue_rentals_qs.count(), "tone": "red"},
            ],
            "dashboard_fleet_cards": fleet_cards,
            "dashboard_financial_cards": financial_cards,
            "dashboard_compliance_groups": [
                {"title": "Vehicle Insurance Due Soon", "items": insurance_due_items, "empty": "No upcoming insurance expiries."},
                {"title": "Vehicle Insurance Expired", "items": insurance_expired_items, "empty": "No expired insurance records."},
                {"title": "Vehicle Registration Expiring", "items": registration_due_items, "empty": "No upcoming registration expiries."},
                {"title": "Annual Inspection Due", "items": annual_inspection_items, "empty": "No upcoming inspection due dates."},
                {"title": "Customer Driving License Expiring", "items": license_expiry_items, "empty": "No upcoming driving license expiries."},
                {"title": "Customer Passport Expiring", "items": passport_expiry_items, "empty": "No upcoming passport expiries."},
            ],
            "dashboard_branch_rows": branch_rows,
            "dashboard_recent_activity": recent_activity,
            "dashboard_modules": dashboard_modules,
        }


custom_admin_site = MyAdminSite(name="custom_admin")
custom_admin_site.disable_action("delete_selected")
