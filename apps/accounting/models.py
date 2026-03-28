
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from apps.branches.models import Branch
from apps.vehicles.models import Vehicle


# نموذج أساسي لإضافة حقول الإنشاء والتعديل على أي موديل يرث منه.
class TimeStampedModel(models.Model):
    # تاريخ ووقت إنشاء السجل أول مرة.
    created_at = models.DateTimeField(auto_now_add=True)
    # تاريخ ووقت آخر تعديل على السجل.
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # هذا الموديل مجرد Base Model ولن ينشأ له جدول مستقل.
        abstract = True


# أنواع الحسابات الرئيسية في شجرة الحسابات.
class AccountType(models.TextChoices):
    # حسابات الأصول.
    ASSET = "asset", "Asset"
    # حسابات الالتزامات.
    LIABILITY = "liability", "Liability"
    # حقوق الملكية.
    EQUITY = "equity", "Equity"
    # الإيرادات.
    REVENUE = "revenue", "Revenue"
    # المصروفات.
    EXPENSE = "expense", "Expense"


# حالات المستندات أو القيود المحاسبية.
class EntryState(models.TextChoices):
    # مسودة قابلة للتعديل.
    DRAFT = "draft", "Draft"
    # مرحلة مرحّلة/معتمدة وغير قابلة للتعديل الحساس.
    POSTED = "posted", "Posted"


# تصنيفات المصروفات الحالية.
class ExpenseCategory(models.TextChoices):
    # صيانة المركبات أو الموجودات.
    MAINTENANCE = "maintenance", "Maintenance"
    # وقود.
    FUEL = "fuel", "Fuel"
    # رواتب.
    SALARY = "salary", "Salary"
    # تصنيف عام لأي مصروف آخر.
    OTHER = "other", "Other"


# تصنيفات الإيرادات الحالية.
class RevenueCategory(models.TextChoices):
    # إيراد الإيجار الأساسي.
    RENTAL = "rental", "Rental Revenue"
    # إيراد تمديد العقد.
    EXTENSION = "extension", "Extension Revenue"
    # غرامة تأخير.
    LATE_FEE = "late_fee", "Late Fee"
    # استرداد أضرار.
    DAMAGE_RECOVERY = "damage_recovery", "Damage Recovery"
    # استرداد مخالفات مرورية.
    TRAFFIC_FINE_RECOVERY = "traffic_fine_recovery", "Traffic Fine Recovery"
    # إيراد آخر غير مصنف.
    OTHER = "other", "Other"


# وسائل الدفع المتاحة حاليًا في النظام.
class PaymentMethod(models.TextChoices):
    # نقدي.
    CASH = "cash", "Cash"
    # تحويل أو حساب بنك.
    TRANSFER = "transfer", "Bank Transfer"
    # بطاقة أو نقطة بيع.
    CARD = "card", "Card/POS"


# موديل الحساب داخل شجرة الحسابات.
class Account(TimeStampedModel):
    # كود الحساب الفريد.
    code = models.CharField(max_length=20, unique=True)
    # اسم الحساب الظاهر للمستخدم.
    name = models.CharField(max_length=200)
    # نوع الحساب: أصل/التزام/إيراد/مصروف...
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    # الحساب الأب في حال كان هذا الحساب تابعًا لمجموعة رئيسية.
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    # هل الحساب نشط وقابل للاستخدام؟
    is_active = models.BooleanField(default=True)
    # هل الحساب ترحيلي مباشرة أم حساب تجميعي Header فقط؟
    is_postable = models.BooleanField(
        default=True,
        help_text="If False, this is a group/header account and cannot receive journal lines.",
    )

    class Meta:
        # ترتيب الحسابات حسب الكود لعرض شجرة مرتبة.
        ordering = ["code"]
        # اسم مفرد داخل الإدارة.
        verbose_name = "Account"
        # اسم جمع داخل الإدارة.
        verbose_name_plural = "Chart of Accounts"

    def __str__(self):
        # عرض الحساب بصيغة: الكود - الاسم.
        return f"{self.code} - {self.name}"

    def clean(self):
        # منع جعل الحساب أبًا لنفسه.
        if self.parent_id and self.parent_id == self.id:
            raise ValidationError("Account cannot be parent of itself.")

        # إذا وُجد أب، فيجب أن يكون الأب حسابًا تجميعيًا وليس ترحيليًا.
        if self.parent and self.parent.is_postable:
            raise ValidationError("Parent account must be a non-postable group account.")

    @property
    def balance(self):
        # مجموع الجانب المدين للحساب.
        debit_total = self.journal_items.aggregate(total=models.Sum("debit"))["total"] or Decimal("0.00")
        # مجموع الجانب الدائن للحساب.
        credit_total = self.journal_items.aggregate(total=models.Sum("credit"))["total"] or Decimal("0.00")

        # الأصول والمصروفات طبيعتها المدينة، لذلك رصيدها = مدين - دائن.
        if self.account_type in (AccountType.ASSET, AccountType.EXPENSE):
            return debit_total - credit_total

        # بقية الأنواع طبيعتها دائنة، لذلك رصيدها = دائن - مدين.
        return credit_total - debit_total


# موديل قيد اليومية الرئيسي.
class JournalEntry(TimeStampedModel):
    # رقم القيد الموحد، ويولد تلقائيًا عند أول حفظ.
    entry_no = models.CharField(max_length=30, unique=True, blank=True)
    # تاريخ القيد المحاسبي.
    entry_date = models.DateField(default=timezone.now)
    # وصف القيد.
    description = models.CharField(max_length=255, blank=True)
    # حالة القيد: مسودة أو مرحل.
    state = models.CharField(
        max_length=10,
        choices=EntryState.choices,
        default=EntryState.DRAFT,
    )

    # اسم التطبيق الذي أنشأ هذا القيد، مثل rentals أو invoices.
    source_app = models.CharField(max_length=50, blank=True)
    # اسم الموديل المصدر لهذا القيد.
    source_model = models.CharField(max_length=50, blank=True)
    # رقم السجل المصدر داخل ذلك الموديل.
    source_id = models.PositiveBigIntegerField(null=True, blank=True)

    # وقت الترحيل الفعلي للقيد.
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # الأحدث فالأقدم بحسب التاريخ ثم المعرف.
        ordering = ["-entry_date", "-id"]
        # اسم مفرد داخل الإدارة.
        verbose_name = "Journal Entry"
        # اسم جمع داخل الإدارة.
        verbose_name_plural = "Journal Entries"

    def __str__(self):
        # عرض رقم القيد كسلسلة نصية.
        return self.entry_no or "Journal Entry"

    @property
    def total_debit(self):
        # مجموع المدين لعناصر القيد.
        return self.items.aggregate(total=models.Sum("debit"))["total"] or Decimal("0.00")

    @property
    def total_credit(self):
        # مجموع الدائن لعناصر القيد.
        return self.items.aggregate(total=models.Sum("credit"))["total"] or Decimal("0.00")

    @property
    def is_balanced(self):
        # يتحقق من توازن القيد محاسبيًا.
        return self.total_debit == self.total_credit

    def clean(self):
        # عند كون القيد مرحلًا يجب أن يحتوي على عناصر فعلية.
        if self.state == EntryState.POSTED:
            if not self.items.exists():
                raise ValidationError("Posted entry must contain at least one journal item.")

            # القيد المرحل يجب أن يكون متوازنًا.
            if not self.is_balanced:
                raise ValidationError("Posted entry must be balanced.")


    @transaction.atomic
    def post(self):
        # --- قفل القيد نفسه من قاعدة البيانات لمنع الترحيل المتزامن لنفس السجل ---
        locked_entry = self.__class__.objects.select_for_update().get(pk=self.pk)

        # --- إذا كان القيد مرحلًا مسبقًا فلا نعيد ترحيله ---
        if locked_entry.state == EntryState.POSTED:
            return

        # --- لا يسمح بترحيل قيد بدون عناصر ---
        if not locked_entry.items.exists():
            raise ValidationError("Cannot post an entry without journal items.")

        # --- حساب المجاميع بعد القفل من قاعدة البيانات ---
        total_debit = locked_entry.items.aggregate(total=models.Sum("debit"))[
            "total"
        ] or Decimal("0.00")
        total_credit = locked_entry.items.aggregate(total=models.Sum("credit"))[
            "total"
        ] or Decimal("0.00")

        # --- لا يسمح بترحيل قيد غير متوازن ---
        if total_debit != total_credit:
            raise ValidationError(
                f"Cannot post unbalanced entry. Debit={total_debit}, Credit={total_credit}"
            )

        # --- تحديث حالة القيد بشكل آمن بشرط أن يبقى Draft ---
        updated_rows = self.__class__.objects.filter(
            pk=locked_entry.pk,
            state=EntryState.DRAFT,
        ).update(
            state=EntryState.POSTED,
            posted_at=timezone.now(),
            updated_at=timezone.now(),
        )

        if updated_rows != 1:
            raise ValidationError("Concurrent posting detected for this journal entry.")

        # --- تحديث الكائن الحالي في الذاكرة ليبقى متزامنًا مع قاعدة البيانات ---
        self.state = EntryState.POSTED
        self.posted_at = locked_entry.posted_at or timezone.now()


    def save(self, *args, **kwargs):
        # توليد رقم القيد تلقائيًا عند أول حفظ فقط.
        if not self.entry_no:
            # الاستيراد داخل الدالة لتجنب الدوران بين models و services وقت التحميل.
            from .services import generate_entry_no

            # إنشاء رقم بصيغة JV-YYYYMMDD-0001.
            self.entry_no = generate_entry_no(entry_date=self.entry_date)

        # تطبيق جميع قواعد التحقق قبل الحفظ.
        self.full_clean()
        # استدعاء حفظ Django الأصلي.
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # منع حذف القيود المرحلة حفاظًا على سلامة الأثر المحاسبي.
        if self.state == EntryState.POSTED:
            raise ValidationError("Posted journal entries cannot be deleted.")

        # السماح بحذف القيود غير المرحلة.
        return super().delete(*args, **kwargs)


# سطر القيد المحاسبي التفصيلي.
class JournalItem(models.Model):
    # القيد الرئيسي الذي ينتمي له هذا السطر.
    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name="items",
    )
    # الحساب المستخدم في هذا السطر.
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="journal_items",
    )
    # وصف اختياري للسطر.
    description = models.CharField(max_length=255, blank=True)
    # مبلغ المدين.
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    # مبلغ الدائن.
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))


class Meta:
    # اسم مفرد داخل الإدارة.
    verbose_name = "Journal Item"
    # اسم جمع داخل الإدارة.
    verbose_name_plural = "Journal Items"
    # --- قيود قاعدة بيانات لمنع الأسطر المحاسبية غير المنطقية حتى لو تم تجاوز clean() ---
    constraints = [
        models.CheckConstraint(
            condition=models.Q(debit__gte=0) & models.Q(credit__gte=0),
            name="journalitem_debit_credit_non_negative",
        ),
        models.CheckConstraint(
            condition=(
                (models.Q(debit__gt=0) & models.Q(credit=0))
                | (models.Q(debit=0) & models.Q(credit__gt=0))
            ),
            name="journalitem_exactly_one_side_positive",
        ),
    ]

    def __str__(self):
        # عرض السطر مع كود الحساب وقيم المدين والدائن.
        return f"{self.account.code} | D:{self.debit} | C:{self.credit}"

    def clean(self):
        # منع القيم السالبة.
        if self.debit < 0 or self.credit < 0:
            raise ValidationError("Debit and credit cannot be negative.")

        # يجب أن يحتوي السطر على قيمة في أحد الجانبين على الأقل.
        if self.debit == 0 and self.credit == 0:
            raise ValidationError("Either debit or credit must be greater than zero.")

        # لا يسمح بوضع مدين ودائن معًا في نفس السطر.
        if self.debit > 0 and self.credit > 0:
            raise ValidationError("A journal item cannot contain both debit and credit.")

        # الحساب التجميعي لا يقبل الترحيل المباشر.
        if not self.account.is_postable:
            raise ValidationError("Cannot post to a group account.")

        # إذا كان القيد مرحلًا فلا يسمح بتعديل أسطره.
        if self.journal_entry.state == EntryState.POSTED:
            raise ValidationError("Cannot modify items of a posted journal entry.")

    def save(self, *args, **kwargs):
        # تنفيذ التحقق الكامل قبل الحفظ.
        self.full_clean()
        # متابعة الحفظ الافتراضي.
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # منع حذف الأسطر من قيد مرحل.
        if self.journal_entry.state == EntryState.POSTED:
            raise ValidationError("Cannot delete items from a posted journal entry.")

        # السماح بالحذف إذا كان القيد ما زال مسودة.
        return super().delete(*args, **kwargs)


# موديل المصروف التشغيلي أو الإداري.
class Expense(TimeStampedModel):
    # الرقم المرجعي الموحد للمصروف، ويولد تلقائيًا عند أول حفظ.
    reference = models.CharField(max_length=30, unique=True, blank=True)
    # تاريخ المصروف.
    expense_date = models.DateField(default=timezone.now)
    # تصنيف المصروف.
    category = models.CharField(
        max_length=30,
        choices=ExpenseCategory.choices,
        default=ExpenseCategory.OTHER,
    )
    # وصف المصروف.
    description = models.CharField(max_length=255)
    # قيمة المصروف.
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # وسيلة الدفع المستخدمة.
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )

    # المركبة المرتبطة بالمصروف إن وجدت.
    vehicle = models.ForeignKey(
        Vehicle,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="expenses",
        verbose_name="Vehicle",
    )
    # الفرع المرتبط بالمصروف إن وجد.
    branch = models.ForeignKey(
        Branch,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="expenses",
        verbose_name="Branch",
    )

    # حساب المصروف الذي سيأخذ الجانب المدين عند الترحيل.
    expense_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="expenses",
    )
    # القيد المحاسبي الناتج عن ترحيل هذا المصروف.
    journal_entry = models.OneToOneField(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="expense_record",
    )
    # حالة المستند المحاسبية.
    state = models.CharField(
        max_length=10,
        choices=EntryState.choices,
        default=EntryState.DRAFT,
    )

    class Meta:
        # عرض الأحدث فالأقدم حسب التاريخ.
        ordering = ["-expense_date", "-id"]
        # اسم مفرد.
        verbose_name = "Expense"
        # اسم جمع.
        verbose_name_plural = "Expenses"

    def __str__(self):
        # عرض رقم المصروف مع المبلغ.
        return f"{self.reference or 'EXP'} - {self.amount}"

    def clean(self):
        # قيمة المصروف يجب أن تكون أكبر من صفر.
        if self.amount <= 0:
            raise ValidationError("Expense amount must be greater than zero.")

        # إذا تم اختيار حساب مصروف فيجب أن يكون من نوع EXPENSE فعليًا.
        if self.expense_account_id and self.expense_account.account_type != AccountType.EXPENSE:
            raise ValidationError("Selected expense account must be of type EXPENSE.")

    def save(self, *args, **kwargs):
        # توليد الرقم المرجعي تلقائيًا عند أول حفظ فقط.
        if not self.reference:
            # استيراد محلي لتجنب أي استيراد دائري وقت تشغيل التطبيق.
            from .services import generate_expense_reference

            # إنشاء الرقم بصيغة EXP-YYYYMM-0001.
            self.reference = generate_expense_reference(expense_date=self.expense_date)

        # تنفيذ قواعد التحقق قبل الحفظ.
        self.full_clean()
        # متابعة الحفظ الافتراضي.
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # منع حذف المصروف إذا تم ترحيله محاسبيًا.
        if self.state == EntryState.POSTED:
            raise ValidationError("Posted expenses cannot be deleted.")

        # السماح بالحذف إذا كان ما يزال مسودة.
        return super().delete(*args, **kwargs)


# مرفق تابع للمصروف.
class ExpenseAttachment(TimeStampedModel):
    # المصروف المرتبط بهذا المرفق.
    expense = models.ForeignKey(
        Expense,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="Expense",
    )
    # ملف المرفق الفعلي.
    file = models.FileField(upload_to="expense_attachments/%Y/%m/")
    # عنوان اختياري للمرفق.
    title = models.CharField(max_length=200, blank=True)

    class Meta:
        # الأحدث أولًا.
        ordering = ["-id"]
        # اسم مفرد.
        verbose_name = "Expense Attachment"
        # اسم جمع.
        verbose_name_plural = "Expense Attachments"

    def __str__(self):
        # عرض عنوان المرفق أو نص بديل مفهوم.
        return self.title or f"Attachment for {self.expense.reference}"


# موديل الإيراد الحالي في تطبيق المحاسبة.
class Revenue(TimeStampedModel):
    # الرقم المرجعي الموحد للإيراد.
    reference = models.CharField(max_length=30, unique=True, blank=True)
    # تاريخ الإيراد.
    revenue_date = models.DateField(default=timezone.now)
    # تصنيف الإيراد.
    category = models.CharField(
        max_length=30,
        choices=RevenueCategory.choices,
        default=RevenueCategory.RENTAL,
    )
    # وصف الإيراد.
    description = models.CharField(max_length=255)
    # قيمة الإيراد.
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # وسيلة الدفع المستخدمة.
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )

    # المركبة المرتبطة بالإيراد إن وجدت.
    vehicle = models.ForeignKey(
        Vehicle,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="revenues",
        verbose_name="Vehicle",
    )
    # الفرع المرتبط بالإيراد إن وجد.
    branch = models.ForeignKey(
        Branch,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="revenues",
        verbose_name="Branch",
    )

    # حساب الإيراد الذي سيأخذ الجانب الدائن عند الترحيل.
    revenue_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="revenues",
    )
    # القيد المحاسبي الناتج عن ترحيل الإيراد.
    journal_entry = models.OneToOneField(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="revenue_record",
    )
    # حالة المستند المحاسبية.
    state = models.CharField(
        max_length=10,
        choices=EntryState.choices,
        default=EntryState.DRAFT,
    )

    class Meta:
        # الأحدث فالأقدم حسب التاريخ.
        ordering = ["-revenue_date", "-id"]
        # اسم مفرد.
        verbose_name = "Revenue"
        # اسم جمع.
        verbose_name_plural = "Revenues"

    def __str__(self):
        # عرض المرجع مع المبلغ.
        return f"{self.reference or 'REV'} - {self.amount}"

    def clean(self):
        # قيمة الإيراد يجب أن تكون أكبر من صفر.
        if self.amount <= 0:
            raise ValidationError("Revenue amount must be greater than zero.")

        # إذا تم اختيار حساب إيراد فيجب أن يكون من نوع REVENUE فعليًا.
        if self.revenue_account_id and self.revenue_account.account_type != AccountType.REVENUE:
            raise ValidationError("Selected revenue account must be of type REVENUE.")

    def save(self, *args, **kwargs):
        # توليد رقم الإيراد تلقائيًا عند أول حفظ فقط.
        if not self.reference:
            # استيراد محلي لتجنب أي استيراد دائري.
            from .services import generate_revenue_reference

            # إنشاء الرقم بصيغة REV-YYYYMM-0001.
            self.reference = generate_revenue_reference(revenue_date=self.revenue_date)

        # تنفيذ التحقق الكامل قبل الحفظ.
        self.full_clean()
        # متابعة الحفظ الافتراضي.
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # منع حذف الإيراد بعد ترحيله.
        if self.state == EntryState.POSTED:
            raise ValidationError("Posted revenues cannot be deleted.")

        # السماح بالحذف إذا بقي كمسودة.
        return super().delete(*args, **kwargs)
