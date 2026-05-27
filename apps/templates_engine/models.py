import uuid

from django.db import models


class EmailTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        "authentication.AdminUser",
        on_delete=models.CASCADE,
        related_name="templates",
    )
    name = models.CharField(max_length=255)
    subject = models.CharField(max_length=500)
    body_html = models.TextField(
        help_text="HTML body. Supports {{name}}, {{college}}, {{phone}}, {{email}} variables.",
    )
    body_plain = models.TextField(blank=True, default="", help_text="Plain text body.")
    is_active = models.BooleanField(default=True)
    is_valid = models.BooleanField(default=True)
    validation_error = models.TextField(blank=True, default="")
    usage_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "email_templates"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name
