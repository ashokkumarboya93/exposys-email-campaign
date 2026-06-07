import json
import logging
import time
from typing import Any

import jinja2
from celery import shared_task, group
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from jinja2.sandbox import SandboxedEnvironment

from apps.campaigns.models import Campaign, CampaignContact, EmailLog
from services.providers.factory import EmailProviderFactory

logger = logging.getLogger(__name__)


def _provider_config() -> tuple[str, dict[str, Any], int]:
    from apps.authentication.models import SystemSettings
    system_settings = SystemSettings.get_solo()
    provider = system_settings.email_provider

    if provider == "ses":
        ses = system_settings.ses_config or {}
        config = {
            "access_key": ses.get("access_key") or getattr(settings, "AWS_ACCESS_KEY_ID", ""),
            "secret_key": ses.get("secret_key") or getattr(settings, "AWS_SECRET_ACCESS_KEY", ""),
            "region": ses.get("region") or getattr(settings, "AWS_REGION", "us-east-1"),
            "from_email": ses.get("from_email") or getattr(settings, "AWS_SES_FROM_EMAIL", ""),
        }
        max_concurrent = int((system_settings.campaign_defaults or {}).get("ses_max_concurrent", 14))
        return provider, config, max_concurrent

    if provider == "gmail":
        gmail = system_settings.gmail_config or {}
        config = {
            "sender_email": gmail.get("sender_email") or "",
            "app_password": gmail.get("app_password") or "",
            "sender_name": gmail.get("sender_name") or "Exposys Campaign",
        }
        max_concurrent = int((system_settings.campaign_defaults or {}).get("gmail_max_concurrent", 5))
        return provider, config, max_concurrent

    brevo = system_settings.brevo_config or {}
    config = {
        "api_key": brevo.get("api_key") or getattr(settings, "BREVO_API_KEY", ""),
        "sender_email": brevo.get("sender_email") or getattr(settings, "BREVO_SENDER_EMAIL", ""),
        "sender_name": brevo.get("sender_name") or getattr(settings, "BREVO_SENDER_NAME", "Exposys Campaign"),
    }
    tier = str(brevo.get("tier", "free")).lower()
    max_concurrent = 50 if tier == "starter" else 30
    max_concurrent = int((system_settings.campaign_defaults or {}).get("brevo_max_concurrent", max_concurrent))
    return "brevo", config, max_concurrent


def _render_context(row: dict[str, Any], campaign_name: str) -> dict[str, Any]:
    name = row.get("contact__name") or ""
    extra_fields = row.get("contact__extra_fields") or {}
    context = {
        "name": name,
        "first_name": name.split(" ")[0] if name else "",
        "last_name": " ".join(name.split(" ")[1:]) if name and len(name.split(" ")) > 1 else "",
        "email": row.get("contact__email") or "",
        "phone": row.get("contact__phone") or "",
        "college": row.get("contact__college") or "",
        "campaign_name": campaign_name,
        "contact_id": str(row["contact_id"]),
    }
    if isinstance(extra_fields, dict):
        context.update(extra_fields)
    return context


@shared_task(
    bind=True,
    queue="email_sending",
    name="apps.campaigns.tasks.process_email_batch",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=3,
)
def process_email_batch(self, campaign_id: str, batch_payload: list[dict[str, Any]]):
    """
    Sub-task that handles an actual chunk of emails.
    Distributed natively across the worker pool.
    """
    try:
        campaign = Campaign.objects.get(id=campaign_id)
    except Campaign.DoesNotExist:
        return

    if campaign.status in ("paused", "completed", "failed"):
        return

    provider_name, config, _ = _provider_config()
    sender = EmailProviderFactory.get_provider(provider_name, config)

    results = []
    
    import asyncio
    
    if provider_name == "gmail":
        # Gmail SMTP: send one-by-one sequentially to avoid throttling
        for payload in batch_payload:
            try:
                result = asyncio.run(sender.send_email(payload))
                results.append(result)
                logger.info("Gmail SMTP result for %s: %s", payload["email"], result.get("status"))
                if result.get("status") == "failed":
                    logger.error("Gmail SMTP failure for %s: %s", payload["email"], result.get("error"))
                # Small delay between emails to avoid Gmail rate limiting
                time.sleep(1)
            except Exception as e:
                logger.exception("Gmail SMTP exception for %s: %s", payload["email"], str(e))
                results.append({
                    "campaign_contact_id": payload["campaign_contact_id"],
                    "contact_id": payload.get("contact_id"),
                    "email": payload["email"],
                    "subject": payload["subject"],
                    "status": "failed",
                    "error": str(e),
                })
    else:
        # Brevo/SES: fire concurrently via asyncio.gather
        async def process_all():
            tasks = [sender.send_email(payload) for payload in batch_payload]
            return await asyncio.gather(*tasks)

        results = asyncio.run(process_all())
    
    now = timezone.now()
    sent_results = [r for r in results if r["status"] == "sent"]
    failed_results = [r for r in results if r["status"] == "failed"]

    sent_cc_ids = [r["campaign_contact_id"] for r in sent_results]
    failed_cc_ids = [r["campaign_contact_id"] for r in failed_results]
    sent_contact_ids = [r["contact_id"] for r in sent_results]
    failed_contact_ids = [r["contact_id"] for r in failed_results]

    with transaction.atomic():
        if sent_cc_ids:
            CampaignContact.objects.filter(id__in=sent_cc_ids).update(
                delivery_status="sent", sent_at=now, last_error_message=""
            )
        if failed_cc_ids:
            # Update each failed contact with its specific error message
            for r in failed_results:
                CampaignContact.objects.filter(id=r["campaign_contact_id"]).update(
                    delivery_status="failed", sent_at=None,
                    last_error_message=r.get("error", "Send failed")[:500]
                )

        if sent_contact_ids:
            from apps.contacts.models import Contact
            Contact.objects.filter(id__in=sent_contact_ids).update(email_status="sent")
        if failed_contact_ids:
            from apps.contacts.models import Contact
            Contact.objects.filter(id__in=failed_contact_ids).update(email_status="failed")

        log_rows = []
        for item in sent_results + failed_results:
            log_rows.append(
                EmailLog(
                    campaign_id=campaign.id,
                    contact_id=item["contact_id"],
                    recipient_email=item["email"],
                    subject_used=item["subject"],
                    status=item["status"],
                    provider_response=item.get("provider_response") or {},
                    error_message=item.get("error") or "",
                    retry_count=item.get("retry_count", 0),
                    sent_at=now,
                )
            )
        if log_rows:
            EmailLog.objects.bulk_create(log_rows, batch_size=500)

        processed_count = len(sent_results) + len(failed_results)
        
        # Atomic F() updates
        Campaign.objects.filter(id=campaign.id).update(
            sent_count=F("sent_count") + len(sent_results),
            failed_count=F("failed_count") + len(failed_results),
            pending_count=F("pending_count") - processed_count,
        )
        
        try:
            # Broadcast via WebSockets
            updated_campaign = Campaign.objects.get(id=campaign.id)
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"campaign_{campaign.id}",
                    {
                        "type": "campaign_progress",
                        "message": {
                            "sent_count": updated_campaign.sent_count,
                            "failed_count": updated_campaign.failed_count,
                            "pending_count": updated_campaign.pending_count,
                            "total": updated_campaign.total_recipients,
                            "status": updated_campaign.status,
                        }
                    }
                )
        except Campaign.DoesNotExist:
            pass


@shared_task(
    bind=True,
    queue="email_sending",
    name="apps.campaigns.tasks.campaign_completed_callback",
    acks_late=True,
)
def campaign_completed_callback(self, results, campaign_id: str):
    Campaign.objects.filter(id=campaign_id).update(
        status="completed",
        completed_at=timezone.now()
    )
    # Broadcast final status
    updated_campaign = Campaign.objects.get(id=campaign_id)
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"campaign_{campaign_id}",
            {
                "type": "campaign_progress",
                "message": {
                    "sent_count": updated_campaign.sent_count,
                    "failed_count": updated_campaign.failed_count,
                    "pending_count": updated_campaign.pending_count,
                    "total": updated_campaign.total_recipients,
                    "status": "completed",
                }
            }
        )


@shared_task(
    bind=True,
    queue="email_sending",
    name="apps.campaigns.tasks.launch_campaign_task",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=3600,
)
def launch_campaign_task(self, campaign_id: str, idempotency_key: str | None = None):
    try:
        campaign = Campaign.objects.select_related("template").get(id=campaign_id)
    except Campaign.DoesNotExist:
        return

    if idempotency_key and str(campaign.idempotency_key) != str(idempotency_key):
        return

    if campaign.status == "completed":
        return

    pending_rows = list(
        CampaignContact.objects.filter(campaign_id=campaign_id)
        .exclude(delivery_status="sent")
        .filter(contact__is_valid=True)
        .values(
            "id",
            "contact_id",
            "contact__email",
            "contact__name",
            "contact__phone",
            "contact__college",
            "contact__extra_fields",
        )
    )

    total = len(pending_rows)

    Campaign.objects.filter(id=campaign_id).update(
        status="running",
        started_at=campaign.started_at or timezone.now(),
        failure_reason="",
    )

    if total == 0:
        Campaign.objects.filter(id=campaign_id).update(status="completed", completed_at=timezone.now())
        return

    jinja_env = SandboxedEnvironment(autoescape=True, undefined=jinja2.Undefined)
    compiled_subject = jinja_env.from_string(campaign.template.subject)
    compiled_body = jinja_env.from_string(campaign.template.body_html)
    compiled_plain = jinja_env.from_string(campaign.template.body_plain or "")

    chunk_size = campaign.batch_size if campaign.batch_size and campaign.batch_size > 0 else 50
    chunk_size = min(chunk_size, 2000)

    # Fanout orchestrator
    sub_tasks = []

    for chunk_start in range(0, len(pending_rows), chunk_size):
        chunk_rows = pending_rows[chunk_start : chunk_start + chunk_size]
        pre_rendered_payload = []
        from django.conf import settings
        import re
        from urllib.parse import quote
        
        base_url = getattr(settings, "TRACKING_BASE_URL", "http://localhost:8000").rstrip('/')

        for row in chunk_rows:
            context = _render_context(row, campaign.name)
            cc_id = str(row["id"])
            
            body_html_rendered = compiled_body.render(**context)
            body_plain_rendered = compiled_plain.render(**context)
            
            # Wrap links
            def link_replacer(match):
                original_url = match.group(1)
                # Don't wrap mailto:, tel:, or internal anchors
                if original_url.startswith(("mailto:", "tel:", "#")):
                    return match.group(0)
                encoded_url = quote(original_url)
                return f'href="{base_url}/analytics/track/click/{cc_id}/?url={encoded_url}"'
            
            body_html_rendered = re.sub(r'href="([^"]+)"', link_replacer, body_html_rendered)
            
            # Inject tracking pixel right before </body>, or at the end if </body> is missing
            pixel_tag = f'<img src="{base_url}/analytics/track/open/{cc_id}/pixel.gif" width="1" height="1" style="display:none;" alt="" />'
            if "</body>" in body_html_rendered.lower():
                body_html_rendered = re.sub(r'(</body>)', rf'{pixel_tag}\1', body_html_rendered, flags=re.IGNORECASE)
            else:
                body_html_rendered += pixel_tag

            pre_rendered_payload.append(
                {
                    "campaign_contact_id": cc_id,
                    "contact_id": str(row["contact_id"]),
                    "email": row["contact__email"],
                    "name": row.get("contact__name") or "",
                    "subject": compiled_subject.render(**context),
                    "body_html": body_html_rendered,
                    "body_plain": body_plain_rendered,
                }
            )
        
        # Add a delay between batches dynamically using Celery countdown
        delay = (chunk_start // chunk_size) * campaign.batch_delay_seconds
        sub_tasks.append(process_email_batch.s(campaign_id, pre_rendered_payload).set(countdown=delay))

    # Create a chord: group of sub-tasks -> callback
    from celery import chord
    chord(sub_tasks)(campaign_completed_callback.s(campaign_id))
