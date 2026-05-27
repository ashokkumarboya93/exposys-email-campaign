import csv
import json
import logging
import socket
from urllib.parse import urlparse

import redis
from celery import current_app
from celery.result import AsyncResult
from django.conf import settings
from django.db import models
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from apps.campaigns.models import Campaign, CampaignContact, EmailLog
from apps.campaigns.serializers import (
    CampaignCreateSerializer,
    CampaignDetailSerializer,
    CampaignListSerializer,
    CampaignStatusSerializer,
    EmailLogSerializer,
)
from apps.campaigns.throttles import NoThrottle

logger = logging.getLogger(__name__)


def _redis_client():
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _is_celery_broker_reachable() -> bool:
    broker_url = getattr(settings, "CELERY_BROKER_URL", "")
    parsed = urlparse(broker_url)
    if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
        return True

    port = parsed.port or 6379
    try:
        with socket.create_connection((parsed.hostname, port), timeout=0.5):
            return True
    except OSError:
        return False


def _has_celery_queue_worker(queue_name: str) -> bool:
    try:
        inspector = current_app.control.inspect(timeout=0.5)
        active_queues = inspector.active_queues() or {}
        for queues in active_queues.values():
            if any(queue.get("name") == queue_name for queue in queues):
                return True
        return False
    except Exception:
        logger.debug("Celery worker inspection failed.", exc_info=True)
        return False


class CampaignViewSet(ModelViewSet):
    queryset = Campaign.objects.select_related("template", "created_by").only(
        "id",
        "idempotency_key",
        "launch_task_id",
        "name",
        "status",
        "total_recipients",
        "sent_count",
        "failed_count",
        "pending_count",
        "batch_size",
        "batch_delay_seconds",
        "started_at",
        "scheduled_at",
        "completed_at",
        "failure_reason",
        "created_at",
        "updated_at",
        "template__id",
        "template__name",
        "template__is_valid",
        "created_by__id",
    )
    permission_classes = [IsAuthenticated]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "create":
            return CampaignCreateSerializer
        if self.action == "list":
            return CampaignListSerializer
        return CampaignDetailSerializer

    def create(self, request, *args, **kwargs):
        import logging
        import json
        logger = logging.getLogger(__name__)
        logger.error(f"DEBUG CAMPAIGN CREATE REQUEST: {json.dumps(request.data)}")
        
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            logger.error(f"DEBUG CAMPAIGN CREATE ERRORS: {json.dumps(serializer.errors)}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        serializer.is_valid(raise_exception=True)
        campaign = serializer.save()
        return Response(CampaignDetailSerializer(campaign).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        campaign = self.get_object()
        force = request.query_params.get("force", "false").lower() == "true"

        # If running, auto-cancel it (don't block – just mark failed first)
        if campaign.status == "running":
            # Revoke any queued Celery task if applicable
            if campaign.launch_task_id:
                try:
                    AsyncResult(campaign.launch_task_id).revoke(terminate=True)
                except Exception:
                    pass
            Campaign.objects.filter(id=campaign.id).update(
                status="failed",
                failure_reason="Deleted by user while running.",
            )
            campaign.refresh_from_db()

        # Hard delete – cascades to CampaignContact and EmailLog via FK on_delete
        campaign.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CampaignLaunchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        campaign = get_object_or_404(Campaign.objects.select_related("template"), pk=pk)

        if not campaign.template.is_valid:
            return Response(
                {"error": campaign.template.validation_error or "Template is invalid."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if campaign.status in ("completed", "failed"):
            # Auto-retry logic if the user accidentally hits Launch instead of Retry
            failed_contacts = CampaignContact.objects.filter(campaign=campaign, delivery_status="failed")
            if failed_contacts.exists():
                contact_ids = list(failed_contacts.values_list("contact_id", flat=True))
                failed_count = failed_contacts.count()
                failed_contacts.update(
                    delivery_status="pending",
                    retry_count=models.F("retry_count") + 1,
                    last_error_message=None,
                )
                from apps.contacts.models import Contact
                Contact.objects.filter(id__in=contact_ids).update(email_status="pending")
                Campaign.objects.filter(pk=campaign.pk).update(
                    pending_count=models.F("pending_count") + failed_count,
                    failed_count=models.F("failed_count") - failed_count,
                    status="draft",
                    failure_reason="",
                )
                campaign.refresh_from_db()
            else:
                return Response(
                    {"error": "Campaign is completed and has no failed emails to retry."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if campaign.status == "running":
            return Response({"status": "running", "message": "Campaign is already running."}, status=status.HTTP_200_OK)

        if campaign.status not in ("draft", "paused", "scheduled"):
            return Response(
                {
                    "error": (
                        f"Cannot launch campaign with status '{campaign.status}'. "
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not CampaignContact.objects.filter(campaign=campaign, delivery_status="pending").exists():
            return Response(
                {"error": "This campaign has no pending contacts. Add contacts before launching."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        campaign.status = "running"
        campaign.started_at = campaign.started_at or timezone.now()
        campaign.failure_reason = ""
        campaign.save(update_fields=["status", "started_at", "failure_reason", "updated_at"])

        from apps.campaigns.tasks import launch_campaign_task

        queued = False
        task_id = ""
        try:
            if _is_celery_broker_reachable() and _has_celery_queue_worker("email_sending"):
                async_result = launch_campaign_task.apply_async(
                    args=[str(campaign.id), str(campaign.idempotency_key)],
                    queue="email_sending",
                )
                task_id = async_result.id
                queued = True
            else:
                # When Celery workers/queue are not available, call the task synchronously.
                launch_campaign_task(str(campaign.id), str(campaign.idempotency_key))
        except Exception as exc:
            Campaign.objects.filter(id=campaign.id).update(status="failed", failure_reason=str(exc))
            logger.exception("Campaign launch failed for %s", campaign.id)
            return Response(
                {"error": f"Campaign launch failed: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if task_id:
            Campaign.objects.filter(id=campaign.id).update(launch_task_id=task_id)

        return Response(
            {
                "campaign_id": str(campaign.id),
                "status": "queued" if queued else "completed",
                "task_id": task_id,
                "queued": queued,
            },
            status=status.HTTP_202_ACCEPTED if queued else status.HTTP_200_OK,
        )


class CampaignPauseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        if campaign.status != "running":
            return Response(
                {"error": f"Cannot pause campaign with status '{campaign.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        Campaign.objects.filter(id=campaign.id).update(status="paused")
        campaign.refresh_from_db()
        return Response(CampaignStatusSerializer(campaign).data, status=status.HTTP_200_OK)


class CampaignResumeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        if campaign.status != "paused":
            return Response(
                {"error": f"Cannot resume campaign with status '{campaign.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.campaigns.tasks import launch_campaign_task

        async_result = launch_campaign_task.apply_async(
            args=[str(campaign.id), str(campaign.idempotency_key)],
            queue="email_sending",
        )
        Campaign.objects.filter(id=campaign.id).update(status="running", launch_task_id=async_result.id)
        return Response(
            {"status": "running", "task_id": async_result.id},
            status=status.HTTP_202_ACCEPTED,
        )


class CampaignRetryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)

        failed_contacts = CampaignContact.objects.filter(campaign=campaign, delivery_status="failed")
        failed_count = failed_contacts.count()
        if failed_count == 0:
            return Response({"error": "No failed emails to retry"}, status=status.HTTP_400_BAD_REQUEST)

        contact_ids = list(failed_contacts.values_list("contact_id", flat=True))
        failed_contacts.update(
            delivery_status="pending",
            retry_count=models.F("retry_count") + 1,
            last_error_message=None,
        )

        from apps.contacts.models import Contact

        Contact.objects.filter(id__in=contact_ids).update(email_status="pending")
        Campaign.objects.filter(pk=campaign.pk).update(
            pending_count=models.F("pending_count") + failed_count,
            failed_count=models.F("failed_count") - failed_count,
            status="running",
            failure_reason="",
        )

        from apps.campaigns.tasks import launch_campaign_task
        from apps.campaigns.views import _is_celery_broker_reachable, _has_celery_queue_worker
        
        task_id = ""
        try:
            if _is_celery_broker_reachable() and _has_celery_queue_worker("email_sending"):
                async_result = launch_campaign_task.apply_async(
                    args=[str(campaign.id), str(campaign.idempotency_key)],
                    queue="email_sending",
                )
                task_id = async_result.id
            else:
                launch_campaign_task(str(campaign.id), str(campaign.idempotency_key))
        except Exception as exc:
            Campaign.objects.filter(id=campaign.id).update(status="failed", failure_reason=str(exc))
            return Response({"error": f"Retry failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if task_id:
            Campaign.objects.filter(id=campaign.id).update(launch_task_id=task_id)

        return Response(
            {
                "retrying": failed_count,
                "message": f"Retry started for {failed_count} emails",
                "task_id": task_id,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class CampaignStatusView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [NoThrottle]

    def get(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        try:
            redis_conn = _redis_client()
            status_key = f"campaign:{campaign.id}:status"

            redis_status = redis_conn.get(status_key)
            if redis_status:
                sent = int(redis_conn.get(f"campaign:{campaign.id}:sent") or 0)
                failed = int(redis_conn.get(f"campaign:{campaign.id}:failed") or 0)
                total = int(redis_conn.get(f"campaign:{campaign.id}:total") or campaign.total_recipients)
                pending = max(total - sent - failed, 0)
                return Response(
                    {
                        "id": str(campaign.id),
                        "status": redis_status,
                        "total_recipients": total,
                        "sent_count": sent,
                        "failed_count": failed,
                        "pending_count": pending,
                        "started_at": campaign.started_at,
                        "completed_at": campaign.completed_at,
                        "failure_reason": campaign.failure_reason,
                    },
                    status=status.HTTP_200_OK,
                )
        except redis.RedisError:
            logger.debug("Redis status lookup failed for campaign %s.", campaign.id, exc_info=True)

        serializer = CampaignStatusSerializer(campaign)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CampaignLogsView(generics.ListAPIView):
    serializer_class = EmailLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        campaign_id = self.kwargs["pk"]
        queryset = EmailLog.objects.filter(campaign_id=campaign_id).select_related("campaign", "contact")

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(recipient_email__icontains=search)

        return queryset.order_by("-created_at")


class CampaignContactsAddView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        contact_ids = request.data.get("contact_ids", [])
        if not contact_ids:
            return Response({"error": "No contact_ids provided"}, status=status.HTTP_400_BAD_REQUEST)

        from apps.contacts.models import Contact

        new_contact_ids = list(
            Contact.objects.filter(id__in=contact_ids, is_valid=True).exclude(
                id__in=CampaignContact.objects.filter(campaign=campaign).values_list("contact_id", flat=True)
            ).values_list("id", flat=True)
        )

        if new_contact_ids:
            CampaignContact.objects.bulk_create(
                [
                    CampaignContact(
                        campaign_id=campaign.id,
                        contact_id=contact_id,
                        delivery_status="pending",
                    )
                    for contact_id in new_contact_ids
                ],
                batch_size=1000,
                ignore_conflicts=True,
            )
            Campaign.objects.filter(pk=campaign.pk).update(
                total_recipients=models.F("total_recipients") + len(new_contact_ids),
                pending_count=models.F("pending_count") + len(new_contact_ids),
            )

        return Response(
            {"message": f"Successfully added {len(new_contact_ids)} contacts to campaign."},
            status=status.HTTP_200_OK,
        )


class EmailLogsExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        campaign_id = request.query_params.get("campaign_id")
        status_filter = request.query_params.get("status")
        from_date = request.query_params.get("from_date")
        to_date = request.query_params.get("to_date")
        email_search = request.query_params.get("email")

        qs = EmailLog.objects.select_related("contact", "campaign").all()

        if campaign_id:
            qs = qs.filter(campaign_id=campaign_id)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if from_date:
            qs = qs.filter(sent_at__date__gte=from_date)
        if to_date:
            qs = qs.filter(sent_at__date__lte=to_date)
        if email_search:
            qs = qs.filter(recipient_email__icontains=email_search)

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="email_logs.csv"'
        writer = csv.writer(response)
        writer.writerow(
            [
                "Recipient Email",
                "Contact Name",
                "Campaign",
                "Subject",
                "Status",
                "Sent At",
                "Retry Count",
                "Error",
            ]
        )
        for log in qs.iterator(chunk_size=1000):
            writer.writerow(
                [
                    log.recipient_email,
                    log.contact.name if log.contact else "",
                    log.campaign.name if log.campaign else "",
                    log.subject_used,
                    log.status,
                    log.sent_at.strftime("%Y-%m-%d %H:%M:%S") if log.sent_at else "",
                    log.retry_count,
                    log.error_message,
                ]
            )

        return response


class TaskStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id):
        async_result = AsyncResult(task_id)
        payload = {
            "task_id": task_id,
            "status": async_result.state,
            "result": async_result.result if async_result.successful() else None,
            "error": str(async_result.result) if async_result.failed() else "",
        }
        return Response(payload, status=status.HTTP_200_OK)
