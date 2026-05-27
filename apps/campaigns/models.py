import uuid

from django.db import models


class Campaign(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("scheduled", "Scheduled"),
        ("running", "Running"),
        ("paused", "Paused"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    launch_task_id = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        "authentication.AdminUser",
        on_delete=models.CASCADE,
        related_name="campaigns",
    )
    name = models.CharField(max_length=255)
    template = models.ForeignKey(
        "templates_engine.EmailTemplate",
        on_delete=models.CASCADE,
        related_name="campaigns",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    total_recipients = models.IntegerField(default=0)
    sent_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    pending_count = models.IntegerField(default=0)
    batch_size = models.IntegerField(default=50)
    batch_delay_seconds = models.IntegerField(default=2)
    started_at = models.DateTimeField(null=True, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "campaigns"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"], name="idx_campaign_status"),
        ]

    def __str__(self):
        return f"{self.name} ({self.status})"


class CampaignContact(models.Model):
    DELIVERY_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
        ("retrying", "Retrying"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="campaign_contacts",
    )
    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.CASCADE,
        related_name="campaign_assignments",
    )
    delivery_status = models.CharField(max_length=20, choices=DELIVERY_STATUS_CHOICES, default="pending")
    sent_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.IntegerField(default=0)
    last_error_message = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "campaign_contacts"
        unique_together = [("campaign", "contact")]
        indexes = [
            models.Index(fields=["campaign"], name="idx_cc_campaign"),
            models.Index(fields=["delivery_status"], name="idx_cc_delivery_status"),
            models.Index(fields=["campaign", "delivery_status"], name="idx_cc_campaign_status"),
        ]

    def __str__(self):
        return f"{self.campaign.name} -> {self.contact.email}"


class EmailLog(models.Model):
    STATUS_CHOICES = [
        ("sent", "Sent"),
        ("failed", "Failed"),
        ("bounced", "Bounced"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="email_logs")
    contact = models.ForeignKey("contacts.Contact", on_delete=models.CASCADE, related_name="email_logs")
    recipient_email = models.EmailField(max_length=255)
    subject_used = models.CharField(max_length=500)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    provider_response = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")
    retry_count = models.IntegerField(default=0)
    sent_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "email_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["campaign"], name="idx_emaillog_campaign"),
            models.Index(fields=["sent_at"], name="idx_emaillog_sent_at"),
            models.Index(fields=["status"], name="idx_emaillog_status"),
            models.Index(fields=["campaign", "status"], name="idx_emaillog_camp_status"),
        ]

    def __str__(self):
        return f"{self.recipient_email} - {self.status}"
