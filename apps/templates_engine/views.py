from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.templates_engine.models import EmailTemplate
from apps.templates_engine.serializers import (
    EmailTemplateListSerializer,
    EmailTemplateSerializer,
    TemplatePreviewRequestSerializer,
    TemplatePreviewResponseSerializer,
)
from services.template_renderer import TemplateRenderError, TemplateRenderer


class EmailTemplateViewSet(viewsets.ModelViewSet):
    queryset = EmailTemplate.objects.filter(is_active=True).only(
        "id",
        "name",
        "subject",
        "body_html",
        "body_plain",
        "is_active",
        "is_valid",
        "validation_error",
        "usage_count",
        "created_by_id",
        "created_at",
        "updated_at",
    )
    permission_classes = [IsAuthenticated]
    search_fields = ["name", "subject"]
    ordering_fields = ["created_at", "name", "usage_count"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return EmailTemplateListSerializer
        return EmailTemplateSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class TemplatePreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        req_serializer = TemplatePreviewRequestSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)
        contact_id = req_serializer.validated_data["contact_id"]

        try:
            template = EmailTemplate.objects.get(pk=pk)
        except EmailTemplate.DoesNotExist:
            return Response({"detail": "Template not found."}, status=status.HTTP_404_NOT_FOUND)

        if not template.is_valid:
            return Response(
                {"detail": template.validation_error or "Template is invalid."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            renderer = TemplateRenderer()
            rendered = renderer.preview(template_id=str(template.id), contact_id=str(contact_id))
        except TemplateRenderError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        response_data = {
            "subject": rendered["subject"],
            "body_html": rendered["body_html"],
            "body_plain": rendered["body_plain"],
            "rendered_at": timezone.now(),
        }
        return Response(TemplatePreviewResponseSerializer(response_data).data, status=status.HTTP_200_OK)
