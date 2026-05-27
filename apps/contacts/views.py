import os
import uuid
import logging
import socket
from urllib.parse import urlparse

from celery import current_app
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from rest_framework import status, viewsets
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.contacts.filters import ContactFilter
from apps.contacts.models import Contact, UploadedFile
from apps.contacts.serializers import (
    ContactListSerializer,
    ContactSerializer,
    FileUploadSerializer,
    UploadedFileSerializer,
)
from apps.contacts.tasks import bulk_delete_contacts, generate_contacts_export, process_uploaded_file

logger = logging.getLogger(__name__)


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


def _should_process_inline() -> bool:
    return not (_is_celery_broker_reachable() and _has_celery_queue_worker("file_processing"))


def _coerce_uuid_list(values):
    ids = []
    for value in values or []:
        try:
            ids.append(uuid.UUID(str(value)))
        except (TypeError, ValueError, AttributeError):
            continue
    return ids


def _resolve_filter_queryset(filter_payload: dict):
    queryset = Contact.objects.filter(is_valid=True)
    if not filter_payload:
        return queryset

    if filter_payload.get("status"):
        queryset = queryset.filter(email_status=filter_payload["status"])
    if filter_payload.get("college"):
        queryset = queryset.filter(college__icontains=filter_payload["college"])
    if filter_payload.get("source_file"):
        queryset = queryset.filter(source_file_id=filter_payload["source_file"])
    if filter_payload.get("search"):
        term = filter_payload["search"].strip()
        if term:
            queryset = queryset.filter(
                Q(name__icontains=term)
                | Q(email__icontains=term)
                | Q(college__icontains=term)
            )
    return queryset


class ContactViewSet(viewsets.ModelViewSet):
    serializer_class = ContactSerializer
    filterset_class = ContactFilter
    search_fields = ["name", "email", "college"]
    ordering_fields = ["created_at", "name", "email", "email_status"]
    ordering = ["-created_at"]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        base = Contact.objects.filter(is_valid=True)
        if self.action == "list":
            return base.only(
                "id",
                "name",
                "email",
                "phone",
                "college",
                "email_status",
                "extra_fields",
                "created_at",
            )
        return base

    def get_serializer_class(self):
        if self.action == "list":
            return ContactListSerializer
        return ContactSerializer

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        Contact.objects.filter(id=instance.id).update(is_valid=False)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContactCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        filters = {
            "status": request.query_params.get("status"),
            "college": request.query_params.get("college"),
            "source_file": request.query_params.get("source_file"),
            "search": request.query_params.get("search"),
        }
        count = _resolve_filter_queryset(filters).count()
        return Response({"count": count}, status=status.HTTP_200_OK)


class FileUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request):
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded = serializer.validated_data["file"]
        original_name = uploaded.name
        extension = original_name.rsplit(".", 1)[-1].lower()
        if extension not in {"csv", "xlsx", "xls"}:
            return Response({"error": "Only csv/xlsx/xls files are accepted."}, status=status.HTTP_400_BAD_REQUEST)

        unique_name = f"{uuid.uuid4().hex}.{extension}"
        upload_dir = os.path.join(settings.MEDIA_ROOT, "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        dest_path = os.path.join(upload_dir, unique_name)

        with open(dest_path, "wb") as handle:
            for chunk in uploaded.chunks(65536):
                handle.write(chunk)

        file_record = UploadedFile.objects.create(
            uploaded_by=request.user,
            original_filename=original_name,
            stored_path=dest_path,
            file_format=extension,
            upload_status="processing",
        )

        tags = serializer.validated_data.get("tags", "")
        queued = False
        try:
            if not _should_process_inline():
                process_uploaded_file.apply_async(args=[str(file_record.id), tags], queue="file_processing")
                queued = True
            else:
                logger.info(
                    "Celery worker is unavailable for contact upload %s. Running inline.",
                    file_record.id,
                )
                process_uploaded_file.run(str(file_record.id), tags)
        except Exception as exc:
            # Fallback for environments where the broker is unavailable but the web app should keep working.
            queued = False
            logger.warning(
                "Celery queue unavailable for contact upload %s. Running inline. Error: %s",
                file_record.id,
                exc,
            )
            try:
                process_uploaded_file.run(str(file_record.id), tags)
            except Exception:
                logger.exception("Fallback inline contact upload processing failed for %s", file_record.id)
                return Response({"error": "Upload processing failed."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        file_record.refresh_from_db()
        return Response(
            {
                "file_id": str(file_record.id),
                "status": file_record.upload_status,
                "queued": queued,
                "processed": file_record.processed_rows,
                "total": file_record.total_rows,
                "valid": file_record.valid_rows,
                "invalid": file_record.invalid_rows,
            },
            status=status.HTTP_202_ACCEPTED if queued else status.HTTP_200_OK,
        )


class ContactExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payload = {
            "filter": {
                "status": request.query_params.get("status"),
                "college": request.query_params.get("college"),
                "source_file": request.query_params.get("source_file"),
                "search": request.query_params.get("search"),
            }
        }
        task = generate_contacts_export.apply_async(args=[payload], queue="bulk_ops")
        return Response(
            {
                "task_id": task.id,
                "message": "Export queued",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class CollegeListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        colleges = (
            Contact.objects.filter(is_valid=True)
            .exclude(college__isnull=True)
            .exclude(college="")
            .values_list("college", flat=True)
            .distinct()
        )
        return Response({"colleges": list(colleges)}, status=status.HTTP_200_OK)


class BulkContactActionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        action = request.data.get("action")
        contact_ids = request.data.get("contact_ids")
        filter_payload = request.data.get("filter")

        if not action:
            return Response({"error": "action is required."}, status=status.HTTP_400_BAD_REQUEST)

        if not contact_ids and not filter_payload:
            return Response(
                {"error": "Provide either contact_ids or filter."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if action == "delete":
            payload = {"contact_ids": contact_ids, "filter": filter_payload}
            if _is_celery_broker_reachable() and _has_celery_queue_worker("bulk_ops"):
                task = bulk_delete_contacts.apply_async(args=[payload], queue="bulk_ops")
                return Response(
                    {"task_id": task.id, "message": "Deletion queued", "queued": True},
                    status=status.HTTP_202_ACCEPTED,
                )
            result = bulk_delete_contacts.run(payload)
            return Response(
                {"message": "Contacts deleted", "queued": False, "result": result, **(result or {})},
                status=status.HTTP_200_OK,
            )

        if action == "export":
            payload = {"contact_ids": contact_ids, "filter": filter_payload}
            if _is_celery_broker_reachable() and _has_celery_queue_worker("bulk_ops"):
                task = generate_contacts_export.apply_async(args=[payload], queue="bulk_ops")
                return Response(
                    {"task_id": task.id, "message": "Export queued", "queued": True},
                    status=status.HTTP_202_ACCEPTED,
                )
            result = generate_contacts_export.run(payload)
            return Response(
                {"message": "Export ready", "queued": False, "result": result, **(result or {})},
                status=status.HTTP_200_OK,
            )

        if action == "add_to_campaign":
            campaign_id = request.data.get("campaign_id")
            if not campaign_id:
                return Response(
                    {"error": "campaign_id is required for add_to_campaign"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            from apps.campaigns.models import Campaign, CampaignContact

            campaign = Campaign.objects.filter(id=campaign_id).first()
            if not campaign:
                return Response({"error": "Campaign not found"}, status=status.HTTP_404_NOT_FOUND)

            if campaign.status not in ("draft", "scheduled"):
                return Response(
                    {"error": "Can only add contacts to draft or scheduled campaigns"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if filter_payload and not contact_ids:
                contact_ids = list(_resolve_filter_queryset(filter_payload).values_list("id", flat=True))

            contact_ids = _coerce_uuid_list(contact_ids)
            if not contact_ids:
                return Response({"error": "No valid contacts selected"}, status=status.HTTP_400_BAD_REQUEST)

            contact_ids = list(
                Contact.objects.filter(id__in=contact_ids, is_valid=True).values_list("id", flat=True)
            )
            if not contact_ids:
                return Response({"error": "Selected contacts were not found"}, status=status.HTTP_400_BAD_REQUEST)

            existing = set(
                CampaignContact.objects.filter(campaign=campaign, contact_id__in=contact_ids).values_list(
                    "contact_id", flat=True
                )
            )
            new_contacts = [cid for cid in contact_ids if cid not in existing]

            if new_contacts:
                with transaction.atomic():
                    before_count = CampaignContact.objects.filter(campaign=campaign).count()
                    CampaignContact.objects.bulk_create(
                        [
                            CampaignContact(campaign=campaign, contact_id=cid, delivery_status="pending")
                            for cid in new_contacts
                        ],
                        batch_size=1000,
                        ignore_conflicts=True,
                    )
                    after_count = CampaignContact.objects.filter(campaign=campaign).count()
                    actual_added = max(after_count - before_count, 0)
                    if actual_added:
                        Campaign.objects.filter(id=campaign.id).update(
                            total_recipients=F("total_recipients") + actual_added,
                            pending_count=F("pending_count") + actual_added,
                        )
            else:
                actual_added = 0

            return Response(
                {"added": actual_added, "skipped": len(contact_ids) - actual_added},
                status=status.HTTP_200_OK,
            )

        return Response({"error": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)


class UploadedFileProgressView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, file_id):
        file_record = UploadedFile.objects.filter(id=file_id).first()
        if not file_record:
            return Response({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)

        total = file_record.total_rows or file_record.processed_rows or 0
        processed = file_record.processed_rows
        percent = int((processed / total) * 100) if total > 0 else 0
        if file_record.upload_status == "completed":
            percent = 100

        return Response(
            {
                "status": file_record.upload_status,
                "processed": processed,
                "total": total,
                "valid": file_record.valid_rows,
                "invalid": file_record.invalid_rows,
                "percent": percent,
            },
            status=status.HTTP_200_OK,
        )


class UploadedFileStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        file_record = UploadedFile.objects.filter(id=pk).first()
        if not file_record:
            return Response({"error": "File not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {
                "id": str(file_record.id),
                "status": file_record.upload_status,
                "total_rows": file_record.total_rows,
                "processed_rows": file_record.processed_rows,
                "valid_count": file_record.valid_rows,
                "error_count": file_record.invalid_rows,
            },
            status=status.HTTP_200_OK,
        )
