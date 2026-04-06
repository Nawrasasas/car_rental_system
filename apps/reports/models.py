from django.db import models

class SalesReport(models.Model):
    class Meta:
        managed = True  # مهم جداً: يمنع Django من إنشاء جدول في قاعدة البيانات
        verbose_name = 'Sales Report'
        verbose_name_plural = 'Sales Reports'

# مسار الملف: apps/reports/models.py

from django.db import models


class GeneralLedger(models.Model):
    """
    نموذج وهمي لإظهار رابط دفتر الأستاذ في لوحة التحكم
    """

    class Meta:
        managed = True  # الأهم: منع إنشاء جدول في قاعدة البيانات
        verbose_name = "General Ledger"
        verbose_name_plural = "📖 General Ledger"


class IncomeStatement(models.Model):
    """
    نموذج وهمي لإظهار رابط قائمة الدخل في لوحة التحكم
    """

    class Meta:
        managed = True
        verbose_name = "Income Statement"
        verbose_name_plural = "📊 Income Statement"
