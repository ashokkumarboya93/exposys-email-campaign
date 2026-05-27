import uuid

from django.contrib.auth.hashers import check_password, make_password
from django.db import models


class AdminUser(models.Model):
    class Role(models.TextChoices):
        SUPERADMIN = "superadmin", "Super Admin"
        ADMIN = "admin", "Admin"
        VIEWER = "viewer", "Viewer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True, max_length=255)
    password_hash = models.CharField(max_length=255)
    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.ADMIN)
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admin_users"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email"], name="idx_admin_users_email"),
            models.Index(fields=["role"], name="idx_admin_users_role"),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.email})"

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password_hash)

    @property
    def is_authenticated(self):
        return True


class SystemSettings(models.Model):
    EMAIL_PROVIDER_CHOICES = [
        ("brevo", "Brevo"),
        ("ses", "AWS SES"),
    ]

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    email_provider = models.CharField(max_length=20, choices=EMAIL_PROVIDER_CHOICES, default="brevo")
    brevo_config = models.JSONField(default=dict, blank=True)
    ses_config = models.JSONField(default=dict, blank=True)
    campaign_defaults = models.JSONField(default=dict, blank=True)
    notification_preferences = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "system_settings"
        verbose_name_plural = "System Settings"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj
