from datetime import date, timedelta

from celery import shared_task
from django.db.models import Count, Q

from apps.analytics.models import Analytics
from apps.campaigns.models import Campaign, EmailLog
from apps.contacts.models import Contact


def _college_distribution(contact_qs):
    rows = (
        contact_qs.filter(is_valid=True)
        .exclude(college__isnull=True)
        .exclude(college="")
        .values("college")
        .annotate(count=Count("id"))
        .order_by("-count")[:15]
    )
    return {row["college"]: row["count"] for row in rows}


@shared_task(bind=True, queue="celery", acks_late=True, reject_on_worker_lost=True)
def aggregate_daily_analytics(self):
    target_date = date.today() - timedelta(days=1)
    logs = EmailLog.objects.filter(sent_at__date=target_date)

    campaign_ids = list(logs.values_list("campaign_id", flat=True).distinct())
    for campaign_id in campaign_ids:
        sent = logs.filter(campaign_id=campaign_id, status="sent").count()
        failed = logs.filter(campaign_id=campaign_id, status="failed").count()
        total_contacts = Campaign.objects.filter(id=campaign_id).values_list("total_recipients", flat=True).first() or 0
        attempted = sent + failed

        Analytics.objects.update_or_create(
            campaign_id=campaign_id,
            date=target_date,
            defaults={
                "total_sent": sent,
                "total_failed": failed,
                "total_pending": max(total_contacts - attempted, 0),
                "success_rate": round((sent / attempted) * 100, 2) if attempted else 0,
                "delivery_rate": round((sent / total_contacts) * 100, 2) if total_contacts else 0,
                "college_distribution": _college_distribution(Contact.objects.filter(is_valid=True)),
            },
        )

    total_sent = logs.filter(status="sent").count()
    total_failed = logs.filter(status="failed").count()
    total_contacts = Contact.objects.filter(is_valid=True).count()
    attempted = total_sent + total_failed

    Analytics.objects.update_or_create(
        campaign=None,
        date=target_date,
        defaults={
            "total_sent": total_sent,
            "total_failed": total_failed,
            "total_pending": Contact.objects.filter(is_valid=True, email_status="pending").count(),
            "success_rate": round((total_sent / attempted) * 100, 2) if attempted else 0,
            "delivery_rate": round((total_sent / total_contacts) * 100, 2) if total_contacts else 0,
            "college_distribution": _college_distribution(Contact.objects.filter(is_valid=True)),
        },
    )


@shared_task(bind=True, queue="celery", acks_late=True, reject_on_worker_lost=True)
def aggregate_campaign_analytics(self, campaign_id: str):
    target_date = date.today()
    logs = EmailLog.objects.filter(campaign_id=campaign_id)
    sent = logs.filter(status="sent").count()
    failed = logs.filter(status="failed").count()
    total_contacts = Campaign.objects.filter(id=campaign_id).values_list("total_recipients", flat=True).first() or 0
    attempted = sent + failed

    Analytics.objects.update_or_create(
        campaign_id=campaign_id,
        date=target_date,
        defaults={
            "total_sent": sent,
            "total_failed": failed,
            "total_pending": max(total_contacts - attempted, 0),
            "success_rate": round((sent / attempted) * 100, 2) if attempted else 0,
            "delivery_rate": round((sent / total_contacts) * 100, 2) if total_contacts else 0,
            "college_distribution": _college_distribution(Contact.objects.filter(is_valid=True)),
        },
    )


@shared_task(bind=True, queue="celery", acks_late=True, reject_on_worker_lost=True)
def process_tracking_event(self, campaign_contact_id: str, event_type: str, ip_address: str = None, user_agent: str = None, metadata: dict = None):
    from apps.analytics.models import EmailEvent, EmailDeliveryStatus
    from django.db import transaction
    
    metadata = metadata or {}
    
    with transaction.atomic():
        # Insert append-only event
        EmailEvent.objects.create(
            campaign_contact_id=campaign_contact_id,
            event_type=event_type,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata
        )
        
        # Determine status precedence
        PRECEDENCE = {
            "pending": 0,
            "sent": 1,
            "delivered": 2,
            "opened": 3,
            "clicked": 4,
            "unsubscribed": 5,
            "unknown": 6,
            "bounced": 7,
            "failed": 8
        }
        
        status_record, created = EmailDeliveryStatus.objects.get_or_create(
            campaign_contact_id=campaign_contact_id,
            defaults={"status": event_type}
        )
        
        if not created:
            current_precedence = PRECEDENCE.get(status_record.status, -1)
            new_precedence = PRECEDENCE.get(event_type, -1)
            
            # If the new event has higher precedence, update it
            if new_precedence > current_precedence:
                status_record.status = event_type
                status_record.save(update_fields=["status", "last_event_at"])
