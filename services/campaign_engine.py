import logging
import time
import uuid

from django.utils import timezone
from celery import group

logger = logging.getLogger(__name__)


class CampaignEngine:
    """
    Orchestrator for launching and executing email campaigns.

    Processes campaign contacts in batches using Celery groups,
    respects pause signals, and triggers analytics aggregation on completion.
    """

    def launch(self, campaign_id: str) -> None:
        """
        Launch a campaign: send emails to all pending contacts in batches.

        This method:
        1. Marks the campaign as 'running'.
        2. Retrieves all CampaignContact records with 'pending' delivery status.
        3. Dispatches emails in batches via Celery groups.
        4. Checks for pause signals between batches.
        5. Marks the campaign as 'completed' when all batches are processed.
        6. Triggers async analytics aggregation.

        Args:
            campaign_id: UUID string (or UUID) of the Campaign to launch.
        """
        from apps.campaigns.models import Campaign, CampaignContact
        from apps.campaigns.tasks import send_email_task

        campaign = Campaign.objects.select_related('template', 'created_by').get(
            id=uuid.UUID(campaign_id) if isinstance(campaign_id, str) else campaign_id
        )

        # Update campaign status to running
        campaign.status = 'running'
        campaign.started_at = timezone.now()
        campaign.save(update_fields=['status', 'started_at', 'updated_at'])

        # Get all pending recipient IDs
        pending_contacts = CampaignContact.objects.filter(
            campaign=campaign,
            delivery_status='pending'
        ).values_list('id', flat=True)

        pending_list = list(pending_contacts)
        batch_size = campaign.batch_size

        # Process in batches
        for i in range(0, len(pending_list), batch_size):
            # Check if campaign was paused between batches
            campaign.refresh_from_db(fields=['status'])
            if campaign.status == 'paused':
                logger.info(f'Campaign {campaign_id} was paused. Stopping.')
                return

            batch = pending_list[i:i + batch_size]

            # Dispatch batch as a Celery group for parallel execution
            job = group(
                send_email_task.s(str(cc_id)) for cc_id in batch
            )
            result = job.apply_async()
            result.get(disable_sync_subtasks=False, timeout=300)  # Wait for batch to finish

            # Delay between batches to avoid rate limiting
            if i + batch_size < len(pending_list):
                time.sleep(campaign.batch_delay_seconds)

        # Mark campaign as completed if it is still running
        campaign.refresh_from_db()
        if campaign.status == 'running':
            campaign.status = 'completed'
            campaign.completed_at = timezone.now()
            campaign.save(update_fields=['status', 'completed_at', 'updated_at'])

        # Trigger analytics aggregation asynchronously
        from apps.analytics.tasks import aggregate_campaign_analytics
        aggregate_campaign_analytics.delay(str(campaign.id))

        # Notifications
        try:
            total = campaign.total_recipients or 1
            failure_rate = (campaign.failed_count / total) * 100
            
            from apps.authentication.models import AdminUser
            from services.email_service import send_notification
            admin = AdminUser.objects.filter(role="superadmin").first()
            if admin:
                send_notification(
                    admin_email=admin.email,
                    subject=f"Campaign '{campaign.name}' completed",
                    body_html=f"""
                        <p>Campaign <strong>{campaign.name}</strong> has completed.</p>
                        <p>Sent: {campaign.sent_count} | Failed: {campaign.failed_count}
                        | Success rate: {round(100 - failure_rate, 1)}%</p>
                    """
                )
                if failure_rate > 10:
                    send_notification(
                        admin_email=admin.email,
                        subject=f"Warning: High failure rate in '{campaign.name}'",
                        body_html=f"""
                            <p>Campaign <strong>{campaign.name}</strong> has a failure rate of
                            {round(failure_rate, 1)}% ({campaign.failed_count} of
                            {campaign.total_recipients} emails failed).</p>
                            <p>Please review the email logs and consider retrying.</p>
                        """
                    )
        except Exception as e:
            logger.error(f"Failed to send campaign completion notification: {e}")

        logger.info(f'Campaign {campaign_id} completed successfully.')
