import uuid

from django.db import models


class UploadedFile(models.Model):
    FORMAT_CHOICES = [
        ("csv", "CSV"),
        ("xlsx", "XLSX"),
        ("xls", "XLS"),
    ]

    STATUS_CHOICES = [
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    uploaded_by = models.ForeignKey(
        "authentication.AdminUser",
        on_delete=models.CASCADE,
        related_name="uploaded_files",
    )
    original_filename = models.CharField(max_length=500)
    stored_path = models.CharField(max_length=1000)
    file_format = models.CharField(max_length=10, choices=FORMAT_CHOICES)
    total_rows = models.IntegerField(default=0)
    processed_rows = models.IntegerField(default=0)
    valid_rows = models.IntegerField(default=0)
    invalid_rows = models.IntegerField(default=0)
    duplicate_rows = models.IntegerField(default=0)
    column_mapping = models.JSONField(default=dict, blank=True)
    upload_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="processing")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "uploaded_files"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.upload_status})"


class Contact(models.Model):
    EMAIL_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
        ("retrying", "Retrying"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_id = models.UUIDField(null=True, blank=True, db_index=True)
    source_file = models.ForeignKey(
        UploadedFile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contacts",
    )
    name = models.CharField(max_length=255)
    email = models.EmailField(max_length=255, db_index=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    college = models.CharField(max_length=255, null=True, blank=True)
    extra_fields = models.JSONField(default=dict, blank=True)
    email_status = models.CharField(max_length=20, choices=EMAIL_STATUS_CHOICES, default="pending")
    is_duplicate = models.BooleanField(default=False)
    is_valid = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "contacts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email"], name="idx_contact_email"),
            models.Index(fields=["email_status"], name="idx_contact_email_status"),
            models.Index(fields=["college"], name="idx_contact_college"),
            models.Index(fields=["created_at"], name="idx_contact_created_at"),
            models.Index(fields=["source_file"], name="idx_contact_source_file"),
            models.Index(fields=["tenant_id"], name="idx_contact_tenant_id"),
            models.Index(fields=["email_status", "college"], name="idx_contact_status_college"),
        ]

    def __str__(self):
        return f"{self.name} <{self.email}>"


class StatusHistory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="status_history")
    campaign = models.ForeignKey(
        "campaigns.Campaign",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="status_changes",
    )
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        "authentication.AdminUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="status_changes",
    )

    class Meta:
        db_table = "status_history"
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.contact.email}: {self.old_status} -> {self.new_status}"
