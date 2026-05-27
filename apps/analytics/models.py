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
