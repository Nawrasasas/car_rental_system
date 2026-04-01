from django.contrib.auth.models import AbstractUser
from django.db import models
from apps.branches.models import Branch

class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('accountant', 'Accountant'),
        ('manager', 'Branch Manager'),
        # --- دور موظفي التوصيل والعمليات الميدانية ---
        ('delivery', 'Delivery Staff'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True)