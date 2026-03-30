import pandas as pd
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django import forms
from apps.vehicles.models import Vehicle
from apps.customers.models import Customer
from .models import Rental
from decimal import InvalidOperation
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.utils import timezone as dj_timezone
from django.utils.dateparse import parse_datetime

from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.branches.models import Branch


# 1. عرض قائمة العقود
def rental_list(request):
    """عرض قائمة بكافة العقود المسجلة مرتبة من الأحدث."""
    rentals = Rental.objects.all().order_by('-id')
    return render(request, 'rentals/list.html', {'rentals': rentals})

from decimal import Decimal
from django.apps import apps
from django.shortcuts import get_object_or_404, render

from .models import Rental
from apps.payments.models import Payment


# --- حاشية: نفس العلامة المستخدمة داخل admin لقبض العقد الأساسي تلقائيًا ---
AUTO_CONTRACT_COLLECTION_NOTE = "__AUTO_CONTRACT_COLLECTION__"


def _find_relation_field_name(model_class, related_model):
    # --- حاشية: نكتشف اسم حقل الربط الحقيقي لأن موديل Deposit / TrafficFine
    # --- قد يكون اسم الحقل فيه مختلفًا بين مشروع وآخر ---
    for field in model_class._meta.get_fields():
        if (
            getattr(field, "is_relation", False)
            and not getattr(field, "auto_created", False)
            and getattr(field, "related_model", None) is related_model
        ):
            return field.name
    return None


def _get_print_collection_amounts(rental):
    # --- حاشية: هذه الحسبة مطابقة لمنطق شاشة العقد في admin ---
    contract_collected = Decimal("0.00")
    deposit_collected = Decimal("0.00")
    fine_collected = Decimal("0.00")

    # =========================================================
    # 1) قبض العقد الأساسي
    # =========================================================
    contract_payment = (
        Payment.objects.filter(
            rental=rental,
            notes=AUTO_CONTRACT_COLLECTION_NOTE,
            accounting_state="posted",
            journal_entry__isnull=False,
        )
        .order_by("-id")
        .first()
    )

    if contract_payment:
        contract_collected = Decimal(contract_payment.amount_paid or 0)

    # =========================================================
    # 2) قبض التأمين
    # =========================================================
    try:
        Deposit = apps.get_model("deposits", "Deposit")
        rental_field_name = _find_relation_field_name(Deposit, Rental)

        if rental_field_name:
            deposit_obj = (
                Deposit.objects.filter(**{f"{rental_field_name}_id": rental.pk})
                .order_by("-pk")
                .first()
            )

            if deposit_obj and getattr(deposit_obj, "journal_entry_id", None):
                # --- حاشية: نعتمد المبلغ الحقيقي من سجل التأمين ---
                deposit_collected = Decimal(getattr(deposit_obj, "amount", 0) or 0)
            elif getattr(rental, "deposit_journal_entry_id", None):
                # --- حاشية: توافق مع البيانات القديمة إذا كان الربط القديم فقط موجودًا ---
                deposit_collected = Decimal(rental.deposit_amount or 0)
    except LookupError:
        # --- حاشية: إذا لم يكن تطبيق deposits موجودًا نتجاهله بهدوء ---
        pass

    # =========================================================
    # 3) قبض المخالفة
    # =========================================================
    try:
        TrafficFine = apps.get_model("traffic_fines", "TrafficFine")
        rental_field_name = _find_relation_field_name(TrafficFine, Rental)

        if rental_field_name:
            fine_obj = (
                TrafficFine.objects.filter(**{f"{rental_field_name}_id": rental.pk})
                .order_by("-pk")
                .first()
            )

            if fine_obj and getattr(
                fine_obj, "customer_collection_journal_entry_id", None
            ):
                fine_collected = Decimal(getattr(fine_obj, "amount", 0) or 0)
    except LookupError:
        # --- حاشية: إذا لم يكن تطبيق traffic_fines موجودًا نتجاهله ---
        pass

    total_paid = contract_collected + deposit_collected + fine_collected
    net_total = Decimal(rental.net_total or 0)
    remaining_balance = net_total - total_paid

    if remaining_balance <= 0:
        payment_status = "Fully Paid"
    elif total_paid > 0:
        payment_status = "Partial Payment"
    else:
        payment_status = "Unpaid"

    return {
        "contract": contract_collected,
        "deposit": deposit_collected,
        "fine": fine_collected,
        "total": total_paid,
        "remaining": remaining_balance,
        "payment_status": payment_status,
    }


# 2. دالة طباعة العقد
def print_rental_view(request, rental_id):
    # --- حاشية: جلب العقد المطلوب ---
    rental = get_object_or_404(Rental, id=rental_id)

    # --- حاشية: نحسب ملخص الطباعة بنفس منطق شاشة العقد ---
    collection = _get_print_collection_amounts(rental)

    context = {
        "rental": rental,
        "summary_net_total": Decimal(rental.net_total or 0),
        "summary_total_paid": collection["total"],
        "summary_remaining_balance": collection["remaining"],
        "summary_payment_status": collection["payment_status"],
        "summary_contract_collected": collection["contract"],
        "summary_deposit_collected": collection["deposit"],
        "summary_fine_collected": collection["fine"],
    }

    return render(request, "rentals/print_contract.html", context)


# 3. استيراد بيانات السيارات من ملف Excel
def import_vehicles_from_excel(request):
    """دالة مخصصة لرفع أسطول السيارات (حوالي 200 سيارة) دفعة واحدة."""
    if request.method == 'POST' and request.FILES.get('excel_file'):
        excel_file = request.FILES['excel_file']
        try:
            df = pd.read_excel(excel_file)
            for _, row in df.iterrows():
                Vehicle.objects.update_or_create(
                    plate_number=row.get('plate_number'),
                    defaults={
                        'brand': row.get('brand', ''),
                        'model': row.get('model', ''),
                        'year': row.get('year', None),
                        'daily_rate': row.get('daily_rate', 0),
                    }
                )
            return redirect('admin:vehicles_vehicle_changelist')
        except Exception as e:
            # يمكن إضافة رسالة خطأ هنا في حال كان ملف الإكسل غير متوافق
            return render(request, 'rentals/import_vehicles.html', {'error': str(e)})
            
    return render(request, 'rentals/import_vehicles.html')

# 4. البحث التلقائي (Autocomplete) - تم التعديل ليتوافق مع JS
def vehicles_autocomplete(request):
    """توفير نتائج البحث لرقم السيارة أثناء الكتابة في نموذج العقد."""
    q = request.GET.get('q', '')
    vehicles = Vehicle.objects.filter(plate_number__icontains=q)[:10]
    # 'number' هنا تطابق li.textContent = vehicle.number الموجودة في rental_form.html
    results = [{'number': v.plate_number} for v in vehicles] 
    return JsonResponse(results, safe=False)

# 5. نموذج العقد المتطور (Rental Form)
class RentalForm(forms.ModelForm):
    plate_number = forms.CharField(
        label="Vehicle Plate Number",
        widget=forms.TextInput(attrs={
            'id': 'vehicle_number_input', 
            'autocomplete': 'off',
            'class': 'form-control',
            'placeholder': 'Start typing plate number...'
        })
    )

    class Meta:
        model = Rental
        # تأكد من إضافة الحقول الجديدة (مثل created_by أو auto_renew) إذا كنت تريد تعديلها يدوياً
        fields = ['plate_number', 'customer', 'branch', 'start_date', 'end_date']
        widgets = {
            # إظهار اختيار التاريخ والوقت (الساعة والدقيقة) بشكل احترافي
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'end_date': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        }

    def clean_plate_number(self):
        plate_no = self.cleaned_data['plate_number']
        try:
            vehicle = Vehicle.objects.get(plate_number=plate_no)
        except Vehicle.DoesNotExist:
            raise forms.ValidationError("السيارة غير موجودة في النظام، يرجى التأكد من رقم اللوحة.")
        return vehicle

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.vehicle = self.cleaned_data['plate_number']
        if commit:
            instance.save()
        return instance

# =========================
# Mobile API helpers/views
# =========================

# --- حاشية: هذا هو التوقيت المعتمد فعليًا للموبايل في هذه المرحلة ---
BAGHDAD_TZ = ZoneInfo("Asia/Baghdad")


def _safe_int(value):
    # --- حاشية: تحويل آمن للمعرفات القادمة من الموبايل ---
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _safe_decimal(value):
    # --- حاشية: تحويل آمن للقيم المالية ---
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None


def _parse_baghdad_datetime(value):
    # --- حاشية: نقبل صيغة وقت عراقية محلية مثل:
    # --- 2026-03-28 10:00:00
    # --- أو 2026-03-28T10:00:00
    # --- وإذا وصل وقت aware بالخطأ نحوله إلى بغداد ثم نحفظه بدون timezone
    text = str(value or "").strip()
    if not text:
        return None

    normalized = text.replace(" ", "T")
    dt = parse_datetime(normalized)

    # --- حاشية: دعم صيغة بدون ثوانٍ ---
    if dt is None and len(normalized) == 16:
        dt = parse_datetime(f"{normalized}:00")

    if dt is None:
        return None

    if dj_timezone.is_aware(dt):
        return dt.astimezone(BAGHDAD_TZ).replace(tzinfo=None)

    return dt


def _validation_message(exc):
    # --- حاشية: استخراج رسالة مفهومة من ValidationError ---
    if hasattr(exc, "message_dict") and exc.message_dict:
        messages = []
        for field_messages in exc.message_dict.values():
            messages.extend([str(msg) for msg in field_messages])
        if messages:
            return " | ".join(messages)

    if hasattr(exc, "messages") and exc.messages:
        return " | ".join([str(msg) for msg in exc.messages])

    return str(exc)


def _serialize_rental(rental):
    # --- حاشية: نفس أسماء الحقول التي يتوقعها Flutter ---
    customer_name = getattr(rental.customer, "full_name", None) or str(rental.customer)

    brand = (rental.vehicle.brand or "").strip()
    model = (rental.vehicle.model or "").strip()
    vehicle_label = f"{rental.vehicle.plate_number} | {brand} {model}".strip()

    return {
        "id": rental.id,
        "contract_number": rental.contract_number or f"#{rental.id}",
        "customer_id": rental.customer_id,
        "customer_name": customer_name,
        "vehicle_id": rental.vehicle_id,
        "vehicle_label": vehicle_label,
        "branch_id": rental.branch_id,
        "status": rental.display_status,
        "start_date": (
            rental.start_date.strftime("%Y-%m-%d %H:%M:%S") if rental.start_date else ""
        ),
        "end_date": (
            rental.end_date.strftime("%Y-%m-%d %H:%M:%S") if rental.end_date else ""
        ),
        "daily_rate": str(rental.daily_rate or 0),
        "net_total": str(rental.net_total or 0),
        "rental_days": rental.rental_days or 0,
    }


@api_view(["GET", "POST"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_rentals_list_create(request):
    # --- حاشية: GET = قائمة العقود / POST = إنشاء عقد جديد من الموبايل ---
    if request.method == "GET":
        rentals = (
            Rental.objects.select_related("customer", "vehicle", "branch")
            .all()
            .order_by("-id")
        )
        return Response(
            {"results": [_serialize_rental(rental) for rental in rentals]},
            status=status.HTTP_200_OK,
        )

    customer_id = _safe_int(request.data.get("customer_id"))
    vehicle_id = _safe_int(request.data.get("vehicle_id"))
    branch_id = _safe_int(request.data.get("branch_id"))
    daily_rate = _safe_decimal(request.data.get("daily_rate"))
    start_date = _parse_baghdad_datetime(request.data.get("start_date"))
    end_date = _parse_baghdad_datetime(request.data.get("end_date"))

    if not customer_id:
        return Response(
            {"detail": "customer_id is required."}, status=status.HTTP_400_BAD_REQUEST
        )

    if not vehicle_id:
        return Response(
            {"detail": "vehicle_id is required."}, status=status.HTTP_400_BAD_REQUEST
        )

    if not branch_id:
        return Response(
            {"detail": "branch_id is required."}, status=status.HTTP_400_BAD_REQUEST
        )

    if daily_rate is None:
        return Response(
            {"detail": "daily_rate is invalid."}, status=status.HTTP_400_BAD_REQUEST
        )

    if start_date is None:
        return Response(
            {
                "detail": "start_date is invalid. Use Baghdad local time like 2026-03-28 10:00:00."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if end_date is None:
        return Response(
            {
                "detail": "end_date is invalid. Use Baghdad local time like 2026-03-29 10:00:00."
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    customer = Customer.objects.filter(pk=customer_id).first()
    if not customer:
        return Response(
            {"detail": "Customer not found."}, status=status.HTTP_404_NOT_FOUND
        )

    vehicle = Vehicle.objects.filter(pk=vehicle_id).first()
    if not vehicle:
        return Response(
            {"detail": "Vehicle not found."}, status=status.HTTP_404_NOT_FOUND
        )

    branch = Branch.objects.filter(pk=branch_id).first()
    if not branch:
        return Response(
            {"detail": "Branch not found."}, status=status.HTTP_404_NOT_FOUND
        )

    rental = Rental(
        customer=customer,
        vehicle=vehicle,
        branch=branch,
        start_date=start_date,
        end_date=end_date,
        daily_rate=daily_rate,
        created_by=request.user,
    )

    try:
        # --- حاشية: save() داخل الموديل سيطبّق كل منطق التحقق وتوليد الرقم وتحديث حالة السيارة ---
        rental.save()
    except ValidationError as exc:
        return Response(
            {"detail": _validation_message(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    rental = Rental.objects.select_related("customer", "vehicle", "branch").get(
        pk=rental.pk
    )

    return Response(_serialize_rental(rental), status=status.HTTP_201_CREATED)


@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def api_rental_detail(request, rental_id):
    # --- حاشية: تفاصيل عقد واحد للموبايل ---
    rental = (
        Rental.objects.select_related("customer", "vehicle", "branch")
        .filter(pk=rental_id)
        .first()
    )

    if not rental:
        return Response(
            {"detail": "Rental not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(_serialize_rental(rental), status=status.HTTP_200_OK)
