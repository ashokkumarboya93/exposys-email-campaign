import jinja2
from jinja2 import TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment
from rest_framework import serializers

from apps.templates_engine.models import EmailTemplate


class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = [
            "id",
            "created_by",
            "name",
            "subject",
            "body_html",
            "body_plain",
            "is_active",
            "is_valid",
            "validation_error",
            "usage_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "is_valid",
            "validation_error",
            "usage_count",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        env = SandboxedEnvironment(autoescape=True, undefined=jinja2.Undefined)
        dummy_context = {
            "name": "Jane Doe",
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
            "phone": "9999999999",
            "college": "IIT",
            "campaign_name": "Sample Campaign",
        }
        subject = attrs.get("subject", getattr(self.instance, "subject", ""))
        body_html = attrs.get("body_html", getattr(self.instance, "body_html", ""))
        body_plain = attrs.get("body_plain", getattr(self.instance, "body_plain", ""))

        try:
            env.from_string(subject).render(**dummy_context)
            env.from_string(body_html).render(**dummy_context)
            if body_plain:
                env.from_string(body_plain).render(**dummy_context)
        except TemplateSyntaxError as exc:
            raise serializers.ValidationError(
                {
                    "template": (
                        "This template has a syntax error: "
                        f"{exc.message} at line {exc.lineno}"
                    )
                }
            ) from exc

        return attrs

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        validated_data["is_valid"] = True
        validated_data["validation_error"] = ""
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data["is_valid"] = True
        validated_data["validation_error"] = ""
        return super().update(instance, validated_data)


class EmailTemplateListSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = [
            "id",
            "name",
            "subject",
            "is_active",
            "is_valid",
            "usage_count",
            "created_at",
        ]


class TemplatePreviewRequestSerializer(serializers.Serializer):
    contact_id = serializers.UUIDField(required=True)


class TemplatePreviewResponseSerializer(serializers.Serializer):
    subject = serializers.CharField()
    body_html = serializers.CharField()
    body_plain = serializers.CharField()
    rendered_at = serializers.DateTimeField()
