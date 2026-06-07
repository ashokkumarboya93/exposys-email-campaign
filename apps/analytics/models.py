import uuid

from django.db import models


class Analytics(models.Model):
    """
    Aggregated analytics snapshot for a single day, optionally scoped to a campaign.

    A record with campaign=None represents global (cross-campaign) totals for that date.
    The unique_together constraint on (campaign, date) ensures one row per campaign per day.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    campaign = models.ForeignKey(
        'campaigns.Campaign',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='analytics_records',
    )
    date = models.DateField()
    total_sent = models.IntegerField(default=0)
    total_failed = models.IntegerField(default=0)
    total_pending = models.IntegerField(default=0)
    success_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    delivery_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
    )
    college_distribution = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'analytics'
        unique_together = [('campaign', 'date')]
        ordering = ['-date']
        verbose_name = 'Analytics'
        verbose_name_plural = 'Analytics'

    def __str__(self) -> str:
        if self.campaign_id is not None:
            return f'Analytics for {self.campaign.name} on {self.date}'
        return f'Analytics for {self.date}'


class EmailDeliveryStatus(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("delivered", "Delivered"),
        ("opened", "Opened"),
        ("clicked", "Clicked"),
        ("bounced", "Bounced"),
        ("failed", "Failed"),
        ("unsubscribed", "Unsubscribed"),
        ("unknown", "Unknown / Not Confirmed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign_contact = models.OneToOneField(
        "campaigns.CampaignContact",
        on_delete=models.CASCADE,
        related_name="delivery_status_record",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    last_event_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "email_delivery_status"
        indexes = [
            models.Index(fields=["status"], name="idx_eds_status"),
        ]

    def __str__(self):
        return f"{self.campaign_contact_id} - {self.status}"


class EmailEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign_contact = models.ForeignKey(
        "campaigns.CampaignContact",
        on_delete=models.CASCADE,
        related_name="events",
    )
    event_type = models.CharField(max_length=20, choices=EmailDeliveryStatus.STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "email_events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["campaign_contact", "event_type"], name="idx_ee_contact_event"),
            models.Index(fields=["created_at"], name="idx_ee_created_at"),
        ]

    def __str__(self):
        return f"{self.event_type} at {self.created_at}"
