import logging

from django.db import transaction
from django.db.models import F, Q
from rest_framework import serializers

from apps.campaigns.models import Campaign, CampaignContact, EmailLog

logger = logging.getLogger(__name__)


class CampaignCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    template_id = serializers.UUIDField(required=False, allow_null=True)
    recipient_filter = serializers.DictField()
    batch_size = serializers.IntegerField(default=50, min_value=1, max_value=500)
    batch_delay_seconds = serializers.IntegerField(default=2, min_value=0, max_value=60)
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True)

    def validate_template_id(self, value):
        from apps.templates_engine.models import EmailTemplate

        if not value:
            # Fallback for old cached UI
            first_template = EmailTemplate.objects.filter(is_valid=True, is_active=True).first()
            if not first_template:
                raise serializers.ValidationError("No active email templates available.")
            return first_template.id

        try:
            template = EmailTemplate.objects.only("id", "is_active", "is_valid", "validation_error").get(id=value)
        except EmailTemplate.DoesNotExist as exc:
            # Fallback for old cached UI if they sent an old deleted ID
            first_template = EmailTemplate.objects.filter(is_valid=True, is_active=True).first()
            if not first_template:
                raise serializers.ValidationError(f"EmailTemplate with id '{value}' does not exist.")
            return first_template.id
            raise serializers.ValidationError(f"EmailTemplate with id '{value}' does not exist.") from exc

        if not template.is_active:
            raise serializers.ValidationError("The selected email template is not active.")
        if not template.is_valid:
            raise serializers.ValidationError(
                template.validation_error or "Selected template is invalid. Fix template syntax before use."
            )

        return value

    def validate_recipient_filter(self, value):
        valid_keys = {"all", "contact_ids", "filter"}
        if not valid_keys.intersection(value.keys()):
            raise serializers.ValidationError(
                "recipient_filter must contain one of: 'all', 'contact_ids', or 'filter'."
            )
        return value

    def _resolve_recipients(self, recipient_filter):
        from apps.contacts.models import Contact

        queryset = Contact.objects.filter(is_valid=True)

        if recipient_filter.get("all") is True:
            return queryset

        if "contact_ids" in recipient_filter:
            contact_ids = recipient_filter["contact_ids"]
            return queryset.filter(id__in=contact_ids)

        if "filter" in recipient_filter:
            filter_params = recipient_filter["filter"]
            if filter_params.get("college"):
                queryset = queryset.filter(college__icontains=filter_params["college"])
            if filter_params.get("status"):
                queryset = queryset.filter(email_status=filter_params["status"])
            if filter_params.get("search"):
                search = filter_params["search"].strip()
                if search:
                    queryset = queryset.filter(
                        Q(name__icontains=search)
                        | Q(email__icontains=search)
                        | Q(college__icontains=search)
                    )
            return queryset

        return Contact.objects.none()

    @transaction.atomic
    def create(self, validated_data):
        from apps.templates_engine.models import EmailTemplate

        template = EmailTemplate.objects.get(id=validated_data["template_id"])
        request = self.context.get("request")

        status = "scheduled" if validated_data.get("scheduled_at") else "draft"
        name = validated_data.get("name")
        if not name:
            import datetime
            name = f"Campaign {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"

        campaign = Campaign.objects.create(
            created_by=request.user,
            name=name,
            template=template,
            status=status,
            batch_size=validated_data.get("batch_size", 50),
            batch_delay_seconds=validated_data.get("batch_delay_seconds", 2),
            scheduled_at=validated_data.get("scheduled_at"),
        )

        contact_ids = list(self._resolve_recipients(validated_data["recipient_filter"]).values_list("id", flat=True))
        recipient_count = len(contact_ids)

        if recipient_count == 0:
            raise serializers.ValidationError(
                {"recipient_filter": "No valid contacts match the selected criteria. Please adjust your filters or upload valid contacts."}
            )

        CampaignContact.objects.bulk_create(
            [
                CampaignContact(campaign_id=campaign.id, contact_id=contact_id, delivery_status="pending")
                for contact_id in contact_ids
            ],
            batch_size=1000,
            ignore_conflicts=True,
        )

        Campaign.objects.filter(id=campaign.id).update(
            total_recipients=recipient_count,
            pending_count=recipient_count,
        )

        EmailTemplate.objects.filter(id=template.id).update(usage_count=F("usage_count") + 1)

        logger.info("Campaign '%s' created with %d recipients.", campaign.name, recipient_count)
        campaign.refresh_from_db()
        return campaign


class _TemplateNestedSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)


class CampaignListSerializer(serializers.ModelSerializer):
    template = _TemplateNestedSerializer(read_only=True)

    class Meta:
        model = Campaign
        fields = [
            "id",
            "name",
            "status",
            "total_recipients",
            "sent_count",
            "failed_count",
            "pending_count",
            "created_at",
            "scheduled_at",
            "template",
        ]
        read_only_fields = fields


class CampaignDetailSerializer(serializers.ModelSerializer):
    template = _TemplateNestedSerializer(read_only=True)

    class Meta:
        model = Campaign
        fields = [
            "id",
            "idempotency_key",
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
            "created_at",
            "updated_at",
            "template",
            "created_by",
            "failure_reason",
        ]
        read_only_fields = fields


class CampaignStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campaign
        fields = [
            "id",
            "status",
            "total_recipients",
            "sent_count",
            "failed_count",
            "pending_count",
            "started_at",
            "completed_at",
            "failure_reason",
        ]
        read_only_fields = fields


class EmailLogSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source="campaign.name", read_only=True)
    contact_email = serializers.CharField(source="contact.email", read_only=True)

    class Meta:
        model = EmailLog
        fields = [
            "id",
            "campaign",
            "campaign_name",
            "contact",
            "contact_email",
            "recipient_email",
            "subject_used",
            "status",
            "provider_response",
            "error_message",
            "retry_count",
            "sent_at",
            "created_at",
        ]
        read_only_fields = fields
