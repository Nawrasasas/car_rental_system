from django.db import models

class SalesReport(models.Model):
    class Meta:
        managed = True  # مهم جداً: يمنع Django من إنشاء جدول في قاعدة البيانات
        verbose_name = 'Sales Report'
        verbose_name_plural = 'Sales Reports'