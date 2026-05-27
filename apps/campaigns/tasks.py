import asyncio
import json
import logging
import time
from typing import Any

import jinja2
import redis
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from jinja2.sandbox import SandboxedEnvironment

from apps.campaigns.models import Campaign, CampaignContact, EmailLog
from services.async_email_sender import AsyncEmailSender

logger = logging.getLogger(__name__)


class _LocalRedis:
    def __init__(self):
        self.values: dict[str, Any] = {}
        self.hashes: dict[str, dict[str, str]] = {}

    def get(self, key: str):
        return self.values.get(key)

    def setex(self, key: str, _ttl: int, value: Any):
        self.values[key] = str(value)

    def incr(self, key: str):
        value = int(self.values.get(key) or 0) + 1
        self.values[key] = str(value)
        return value

    def hset(self, key: str, field: str, value: str):
        self.hashes.setdefault(key, {})[field] = value

    def hvals(self, key: str):
        return list(self.hashes.get(key, {}).values())


def _redis_client():
    client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        client.ping()
        return client
    except redis.RedisError:
        logger.info("Redis unavailable for campaign task. Using in-process status cache.")
        return _LocalRedis()


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

    # Brevo — always prefer .env values as primary source, DB overrides if set
    brevo = system_settings.brevo_config or {}
    env_api_key = getattr(settings, "BREVO_API_KEY", "")
    env_sender_email = getattr(settings, "BREVO_SENDER_EMAIL", "")
    env_sender_name = getattr(settings, "BREVO_SENDER_NAME", "Exposys Campaign")

    config = {
        "api_key": brevo.get("api_key") or env_api_key,
        "sender_email": brevo.get("sender_email") or env_sender_email,
        "sender_name": brevo.get("sender_name") or env_sender_name,
    }

    if not config["api_key"]:
        logger.error("NO BREVO API KEY FOUND. Check .env or SystemSettings.")

    tier = str(brevo.get("tier", "free")).lower()
    if tier == "starter":
        max_concurrent = 50
    else:
        max_concurrent = 30
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


async def _process_chunk(
    sender: AsyncEmailSender,
    campaign_id: str,
    chunk_payload: list[dict[str, Any]],
    max_concurrent: int,
    redis_conn,
):
    cache_key = f"campaign:{campaign_id}:results"

    def _record_result(result: dict[str, Any]):
        status = result["status"]
        if status == "sent":
            redis_conn.incr(f"campaign:{campaign_id}:sent")
        elif status == "failed":
            redis_conn.incr(f"campaign:{campaign_id}:failed")

        if status in {"sent", "failed"}:
            redis_conn.hset(cache_key, str(result["campaign_contact_id"]), json.dumps(result))

    first_pass = await sender.send_all_parallel(
        payloads=chunk_payload,
        max_concurrent=max_concurrent,
        result_callback=_record_result,
        allow_deferred=True,
    )

    deferred_payload = [
        item for item, result in zip(chunk_payload, first_pass) if result.get("deferred") is True
    ]

    final_results = [result for result in first_pass if not result.get("deferred")]

    if deferred_payload:
        await asyncio.sleep(60)
        second_pass = await sender.send_all_parallel(
            payloads=deferred_payload,
            max_concurrent=10,
            result_callback=_record_result,
            allow_deferred=False,
        )
        final_results.extend(second_pass)

    return final_results


def _write_results_to_db(campaign: Campaign, results: list[dict[str, Any]], is_completed: bool = False):
    if not results and not is_completed:
        return

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
                delivery_status="sent",
                sent_at=now,
                last_error_message="",
            )
        if failed_cc_ids:
            CampaignContact.objects.filter(id__in=failed_cc_ids).update(
                delivery_status="failed",
                sent_at=None,
                last_error_message="Send failed",
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
        
        update_fields = {
            "sent_count": F("sent_count") + len(sent_results),
            "failed_count": F("failed_count") + len(failed_results),
            "pending_count": F("pending_count") - processed_count,
        }
        
        if is_completed:
            update_fields["status"] = "completed"
            update_fields["completed_at"] = now
            update_fields["failure_reason"] = ""

        Campaign.objects.filter(id=campaign.id).update(**update_fields)


@shared_task(
    bind=True,
    queue="email_sending",
    name="apps.campaigns.tasks.launch_campaign_task",
    acks_late=True,
    reject_on_worker_lost=True,
    soft_time_limit=600,
    time_limit=660,
)
def launch_campaign_task(self, campaign_id: str, idempotency_key: str | None = None):
    started = time.time()
    redis_conn = _redis_client()
    cache_key = f"campaign:{campaign_id}:results"
    ttl = 86400

    try:
        campaign = Campaign.objects.select_related("template").get(id=campaign_id)
    except Campaign.DoesNotExist:
        logger.error(json.dumps({"campaign_id": campaign_id, "event": "campaign_missing"}))
        return

    if idempotency_key and str(campaign.idempotency_key) != str(idempotency_key):
        logger.warning(
            json.dumps(
                {
                    "campaign_id": campaign_id,
                    "event": "idempotency_key_mismatch",
                    "provided": idempotency_key,
                    "current": str(campaign.idempotency_key),
                }
            )
        )
        return

    if campaign.status == "completed":
        logger.info(
            json.dumps(
                {
                    "campaign_id": campaign_id,
                    "event": "already_completed",
                    "idempotency_key": str(campaign.idempotency_key),
                }
            )
        )
        return

    if redis_conn.get(f"campaign:{campaign_id}:db_committed") == "1":
        return

    cached_results = redis_conn.hvals(cache_key)
    if cached_results:
        parsed_results = [json.loads(value) for value in cached_results]
        try:
            _write_results_to_db(campaign, parsed_results)
            redis_conn.setex(f"campaign:{campaign_id}:status", ttl, "completed")
            redis_conn.setex(f"campaign:{campaign_id}:db_committed", ttl, "1")
            return
        except Exception as exc:
            logger.exception("Cached DB write failed for campaign %s: %s", campaign_id, exc)
            Campaign.objects.filter(id=campaign_id).update(status="failed", failure_reason=str(exc))
            redis_conn.setex(f"campaign:{campaign_id}:status", ttl, "failed")
            raise

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
    redis_conn.setex(f"campaign:{campaign_id}:sent", ttl, 0)
    redis_conn.setex(f"campaign:{campaign_id}:failed", ttl, 0)
    redis_conn.setex(f"campaign:{campaign_id}:total", ttl, total)
    redis_conn.setex(f"campaign:{campaign_id}:status", ttl, "running")

    Campaign.objects.filter(id=campaign_id).update(
        status="running",
        started_at=campaign.started_at or timezone.now(),
        failure_reason="",
    )

    if total == 0:
        Campaign.objects.filter(id=campaign_id).update(status="completed", completed_at=timezone.now())
        redis_conn.setex(f"campaign:{campaign_id}:status", ttl, "completed")
        redis_conn.setex(f"campaign:{campaign_id}:db_committed", ttl, "1")
        return

    jinja_env = SandboxedEnvironment(autoescape=True, undefined=jinja2.Undefined)
    compiled_subject = jinja_env.from_string(campaign.template.subject)
    compiled_body = jinja_env.from_string(campaign.template.body_html)
    compiled_plain = jinja_env.from_string(campaign.template.body_plain or "")

    provider, provider_cfg, max_concurrent = _provider_config()
    sender = AsyncEmailSender(provider=provider, provider_config=provider_cfg)

    # Use the user-defined batch size, default to 50 if missing, max 2000 per chunk
    chunk_size = campaign.batch_size if campaign.batch_size and campaign.batch_size > 0 else 50
    chunk_size = min(chunk_size, 2000)

    for chunk_start in range(0, len(pending_rows), chunk_size):
        chunk_rows = pending_rows[chunk_start : chunk_start + chunk_size]
        pre_rendered_payload = []
        for row in chunk_rows:
            context = _render_context(row, campaign.name)
            pre_rendered_payload.append(
                {
                    "campaign_contact_id": str(row["id"]),
                    "contact_id": str(row["contact_id"]),
                    "email": row["contact__email"],
                    "name": row.get("contact__name") or "",
                    "subject": compiled_subject.render(**context),
                    "body_html": compiled_body.render(**context),
                    "body_plain": compiled_plain.render(**context),
                }
            )

        chunk_results = asyncio.run(
            _process_chunk(
                sender=sender,
                campaign_id=str(campaign.id),
                chunk_payload=pre_rendered_payload,
                max_concurrent=max_concurrent,
                redis_conn=redis_conn,
            )
        )
        
        # Write results to DB immediately so the UI shows live logs!
        try:
            _write_results_to_db(campaign, chunk_results, is_completed=False)
        except Exception as exc:
            logger.exception("Incremental DB write failed for campaign %s: %s", campaign.id, exc)

    try:
        _write_results_to_db(campaign, [], is_completed=True)
        redis_conn.setex(f"campaign:{campaign_id}:status", ttl, "completed")
        redis_conn.setex(f"campaign:{campaign_id}:db_committed", ttl, "1")
    except Exception as exc:
        logger.exception("Final DB status update failed for campaign %s: %s", campaign_id, exc)
        Campaign.objects.filter(id=campaign_id).update(status="failed", failure_reason=str(exc))
        redis_conn.setex(f"campaign:{campaign_id}:status", ttl, "failed")
        raise exc

    sent = int(redis_conn.get(f"campaign:{campaign_id}:sent") or 0)
    failed = int(redis_conn.get(f"campaign:{campaign_id}:failed") or 0)
    duration = round(time.time() - started, 3)

    logger.info(
        json.dumps(
            {
                "campaign_id": str(campaign.id),
                "event": "send_complete",
                "sent": sent,
                "failed": failed,
                "duration_seconds": duration,
                "provider": provider,
            }
        )
    )
