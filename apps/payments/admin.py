# PATH: apps/payments/admin.py
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.html import format_html
from core.admin_site import custom_admin_site
from .models import Payment
from .services import process_payment
from apps.attachments.inlines import AttachmentInline
from django.contrib import messages
from django.http import HttpResponseRedirect

from django.utils import timezone
from .models import Payment, PaymentRefund
from apps.accounting.services import post_payment_receipt, post_payment_refund

@admin.register(Payment, site=custom_admin_site)
class PaymentAdmin(admin.ModelAdmin):
    # الأعمدة الظاهرة في قائمة السندات.
    list_display = (
        "reference",
        "rental",
        "amount_paid",
        "currency_code",
        "method",
        "status_tag",
        "payment_date",
        "accounting_state",
    )

    # الفلاتر الجانبية.
    list_filter = ("status", "method", "payment_date", "accounting_state")

    # حقول البحث.
    search_fields = ("reference", "rental__id", "notes")

    # مرجع السند والقيد الناتج حقول آلية للقراءة فقط.
    # amount_usd دائماً للقراءة فقط لأنه يُحسب تلقائيًا من amount_paid * exchange_rate
    readonly_fields = (
        "reference",
        "journal_entry",
        "accounting_state",
        "post_payment_button",
        "refund_payment_button",
        "amount_usd",
        "exchange_rate_to_usd",
        "exchange_rate_date",
    )

    # لا نخفي exchange_rate_date بعد الآن لأنه سيظهر كسجل مرجعي فقط
    exclude = ("status",)

    fieldsets = (
        (
            "Payment Information",
            {
                "fields": (
                    "reference",
                    "rental",
                    "amount_paid",
                    "currency_code",
                    "amount_usd",
                    "method",
                    "payment_date",
                    "notes",
                )
            },
        ),
        (
            "Currency Snapshot",
            {
                "fields": (
                    "exchange_rate_to_usd",
                    "exchange_rate_date",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Accounting Information",
            {
                "fields": (
                    "journal_entry",
                    "accounting_state",
                )
            },
        ),
    )

    inlines = [AttachmentInline]

    class Media:
        css = {"all": ("css/attachment_gallery_inline.css",)}

        js = (
            "admin/js/payment_currency_ui.js",
            "js/attachment_gallery_inline.js",
        )

    def post_payment_button(self, obj=None):
        # قبل أول حفظ لا يوجد سجل فعلي بعد
        if not obj or not obj.pk:
            return "Save the payment first."

        # إذا كانت الدفعة مرحّلة بالفعل أو لديها قيد محاسبي
        # نظهر حالة ثابتة بدل الزر
        if obj.accounting_state == "posted" or obj.journal_entry_id:
            return format_html(
                '<span style="color:#28a745; font-weight:bold;">{}</span>',
                "✓ Posted",
            )

        # إذا كانت الدفعة محفوظة ولم تُرحّل بعد
        # نظهر زر الترحيل
        return format_html(
            '<button type="submit" name="_post_payment" '
            'style="background:#1d4ed8; color:white; padding:8px 16px; '
            'border:none; border-radius:6px; font-weight:bold; cursor:pointer;">{}</button>',
            "Post to Accounting",
        )

    post_payment_button.short_description = "Post"

    def refund_payment_button(self, obj=None):
        # لا يظهر شيء في شاشة الإضافة
        if not obj or not obj.pk:
            return ""

        # لا يظهر زر Refund قبل ترحيل الدفعة
        if obj.accounting_state != "posted" or not obj.journal_entry_id:
            return ""

        refund_record = PaymentRefund.objects.filter(payment=obj).first()

        # إذا كان المرتجع مرحلًا نظهر حالة ثابتة
        if refund_record and refund_record.journal_entry_id:
            return format_html(
                '<span style="color:#dc2626; font-weight:bold;">{}</span>',
                "↩ Refunded",
            )

        # إذا كان هناك سجل مرتجع Draft نمنع إنشاء سجل آخر
        if refund_record:
            return format_html(
                '<span style="color:#92400e; font-weight:bold;">{}</span>',
                "Refund draft exists",
            )

        return format_html(
            '<button type="submit" name="_refund_payment" '
            'style="background:#dc2626; color:white; padding:8px 16px; '
            'border:none; border-radius:6px; font-weight:bold; cursor:pointer;">{}</button>',
            "Refund Payment",
        )

    refund_payment_button.short_description = "Refund"

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))

        # فقط بعد إنشاء السجل فعليًا نظهر حقل زر Post
        if obj and obj.pk:
            updated_fieldsets = []

            for title, options in fieldsets:
                options = dict(options)
                fields = list(options.get("fields", ()))

                if title == "Accounting Information":
                    if "post_payment_button" not in fields:
                        fields.append("post_payment_button")
                    if "refund_payment_button" not in fields:
                        fields.append("refund_payment_button")    

                options["fields"] = tuple(fields)
                updated_fieldsets.append((title, options))

            return updated_fieldsets

        return fieldsets

    def response_change(self, request, obj):
        if "_post_payment" in request.POST:
            try:
                # نعيد تحميل الكائن من قاعدة البيانات قبل الترحيل
                obj.refresh_from_db()

                # منع الترحيل المكرر
                if obj.accounting_state == "posted" or obj.journal_entry_id:
                    self.message_user(
                        request,
                        "This payment is already posted.",
                        level=messages.ERROR,
                    )
                else:
                    post_payment_receipt(payment=obj)
                    self.message_user(
                        request,
                        "Payment posted to accounting successfully.",
                        level=messages.SUCCESS,
                    )
            except Exception as e:
                self.message_user(request, str(e), level=messages.ERROR)

            return HttpResponseRedirect(request.path)

        if "_refund_payment" in request.POST:
            try:
                obj.refresh_from_db()

                if obj.accounting_state != "posted" or not obj.journal_entry_id:
                    self.message_user(
                        request,
                        "Only posted payments can be refunded.",
                        level=messages.ERROR,
                    )
                    return HttpResponseRedirect(request.path)

                existing_refund = PaymentRefund.objects.filter(payment=obj).first()

                if existing_refund and existing_refund.journal_entry_id:
                    self.message_user(
                        request,
                        "This payment is already refunded.",
                        level=messages.ERROR,
                    )
                    return HttpResponseRedirect(request.path)

                if not existing_refund:
                    existing_refund = PaymentRefund.objects.create(
                        payment=obj,
                        amount=obj.amount_paid,
                        refund_date=timezone.localdate(),
                        notes=f"Auto refund for payment {obj.reference or obj.pk}",
                    )

                post_payment_refund(payment_refund=existing_refund)

                self.message_user(
                    request,
                    "Payment refunded successfully.",
                    level=messages.SUCCESS,
                )
            except Exception as e:
                self.message_user(request, str(e), level=messages.ERROR)

            return HttpResponseRedirect(request.path)

    def status_tag(self, obj):
        # إذا كانت الحالة مكتملة نعرض الوسم باللون الأخضر.
        if obj.status == "completed":
            color = "#28a745"
            text = "COMPLETED"
        # إذا كانت الحالة معلقة نعرض لونًا مميزًا لها.
        elif obj.status == "pending":
            color = "#dc3545"
            text = "PENDING"
        # بقية الحالات تعرض بلون رمادي.
        else:
            color = "#6c757d"
            text = obj.get_status_display().upper()

        # بناء الـ HTML النهائي مع تمرير المتغيرات بصورة آمنة.
        return format_html(
            '<span style="background-color: {}; color: white; padding: 5px 12px; '
            'border-radius: 15px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            text,
        )

    # تسمية العمود داخل القائمة.
    status_tag.short_description = "STATUS"

    def get_actions(self, request):
        # --- إزالة الحذف الجماعي الافتراضي لأنه قد يتجاوز delete() في الموديل ---
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    def currency_ui_hint(self, obj=None):
        return format_html(
            '<div id="payment-currency-preview" '
            'style="padding:10px 12px; background:#eff6ff; border:1px solid #bfdbfe; '
            'border-radius:8px; color:#1e3a8a; font-weight:600; display:inline-block;">'
            'Amount will be entered in the selected currency.'
            '</div>'
        )

    currency_ui_hint.short_description = "Currency Preview"

    def get_readonly_fields(self, request, obj=None):
        # نبدأ من الحقول الآلية الأساسية.
        base_fields = list(self.readonly_fields)

        # إذا كانت العملة USD فسعر الصرف ثابت = 1 ولا يحتاج إدخال
        # نجعله للقراءة فقط ويُعبأ تلقائيًا في الموديل
        if obj and getattr(obj, "currency_code", None) == "USD":
            if "exchange_rate_to_usd" not in base_fields:
                base_fields.append("exchange_rate_to_usd")

        # إذا كان السند مرحلًا نجعل بقية الحقول الحساسة للقراءة فقط.
        if obj and (obj.accounting_state == "posted" or obj.journal_entry_id):
            base_fields.extend(
                [
                    "rental",
                    "amount_paid",
                    "currency_code",
                    "exchange_rate_to_usd",
                    "method",
                    "status",
                    "payment_date",
                    "notes",
                    "accounting_state",
                ]
            )

        # إعادة الحقول النهائية (مع إزالة التكرار).
        return tuple(dict.fromkeys(base_fields))

    def has_delete_permission(self, request, obj=None):
        # منع حذف السند إذا كان مرحلًا أو مرتبطًا بقيد.
        if obj and (obj.accounting_state == "posted" or obj.journal_entry_id):
            return False
        # خلاف ذلك نرجع إلى سلوك Django الافتراضي.
        return super().has_delete_permission(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # لا نعرض في شاشة الدفع إلا العقود النشطة فقط
        if db_field.name == "rental":
            kwargs["queryset"] = (
                db_field.remote_field.model.objects.filter(status="active")
                .select_related("customer")
                .order_by("-id")
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        # ======================================================
        # مهم جدًا:
        # عند الضغط على أزرار العمليات المخصصة مثل Post / Refund
        # لا نريد إعادة حفظ السند عبر process_payment()
        # لأن Django Admin يستدعي save_model قبل response_change
        # وهذا يسبب الخطأ:
        # Posted payments cannot be edited.
        # ======================================================
        if "_post_payment" in request.POST or "_refund_payment" in request.POST:
            return

        # --- نحدد هل هذه عملية إنشاء أم تعديل ---
        is_creation = not change

        # --- في نظامنا الحالي لا نستخدم Pending ---
        # --- أي Payment يتم إنشاؤه من هذه الشاشة يعتبر مقبوضًا فعليًا ---
        obj.status = "completed"

        # ======================================================
        # ملء سعر الصرف تلقائيًا من جدول Exchange Rates
        # إذا لم يُدخله المستخدم يدويًا
        # ======================================================
        if obj.currency_code and obj.currency_code != "USD":
            if not obj.exchange_rate_to_usd:
                try:
                    from apps.exchange_rates.services import (
                        get_exchange_rate,
                        ExchangeRateNotFound,
                    )
                    rate_date = obj.payment_date or None
                    obj.exchange_rate_to_usd = get_exchange_rate(
                        obj.currency_code, rate_date
                    )
                except Exception:
                    # إذا لم يوجد سعر صرف، سيرفضه clean() في الموديل برسالة واضحة
                    pass

        try:
            # --- تمرير السند كاملًا إلى طبقة الخدمات بدل الحفظ المباشر من الأدمن ---
            process_payment(obj, is_creation=is_creation)

        except ValidationError as e:
            # --- نعيد نفس الخطأ كما هو حتى يحتفظ Django ببنية الأخطاء الصحيحة ---
            raise e
