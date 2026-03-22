from django import forms

from .models import Invoice


# فورم الفاتورة الرئيسي.
class InvoiceForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        # تنفيذ تهيئة الفورم الأساسية أولًا.
        super().__init__(*args, **kwargs)

        # جعل اختيار العميل اختياريًا مؤقتًا للمحافظة على التوافق
        # مع الفواتير القديمة التي قد تعتمد فقط على الاسم النصي.
        self.fields["customer"].required = False

        # جعل الحساب المدين اختياريًا الآن حتى لا نكسر أي إدخال قديم،
        # ويمكن لاحقًا تحويله إلى إجباري عند بدء Post المحاسبي الرسمي.
        self.fields["receivable_account"].required = False

        # جعل حساب الإيراد اختياريًا الآن لنفس السبب.
        self.fields["revenue_account"].required = False

        # تحسين أسماء الحقول الظاهرة للمستخدم.
        self.fields["customer"].label = "Customer"
        self.fields["receivable_account"].label = "Receivable Account"
        self.fields["revenue_account"].label = "Revenue Account"

    class Meta:
        # ربط الفورم بموديل الفاتورة.
        model = Invoice

        # ملاحظة مهمة:
        # أزلنا status من الفورم حتى لا يغيره المستخدم يدويًا.
        # الحالة ستبقى تحت تحكم النظام فقط.
        fields = [
            "invoice_date",
            "due_date",
            "from_company",
            "customer",
            "receivable_account",
            "revenue_account",
            "customer_name",
            "customer_email",
            "customer_phone",
            "customer_address",
            "notes",
        ]

        # تخصيص الـ widgets للحقول الظاهرة فقط.
        widgets = {
            "invoice_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "customer": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "receivable_account": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "revenue_account": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "due_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "from_company": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Your Company Name",
                }
            ),
            "customer_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Customer Name",
                }
            ),
            "customer_email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "client@example.com",
                }
            ),
            "customer_phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "+964 ...",
                }
            ),
            "customer_address": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Customer Address",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Notes...",
                }
            ),
        }
