from datetime import timedelta

from django.db.models import Count, Q
from django.db.models.functions import ExtractHour, ExtractWeekDay, TruncDate
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.campaigns.models import Campaign, EmailLog
from apps.campaigns.serializers import EmailLogSerializer
from apps.contacts.models import Contact


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        days = int(request.query_params.get("days", 7))
        days = 7 if days not in (7, 30) else days
        start_date = timezone.now().date() - timedelta(days=days - 1)

        total_contacts = Contact.objects.filter(is_valid=True).count()
        total_campaigns = Campaign.objects.count()

        base_logs = EmailLog.objects.all()
        scoped_logs = base_logs.filter(sent_at__date__gte=start_date)

        sent_count = scoped_logs.filter(status="sent").count()
        failed_count = scoped_logs.filter(status="failed").count()
        pending_count = Contact.objects.filter(is_valid=True, email_status="pending").count()

        attempted = sent_count + failed_count
        success_rate = round((sent_count / attempted) * 100, 2) if attempted else 0
        delivery_rate = round((sent_count / total_contacts) * 100, 2) if total_contacts else 0

        daily_trend_rows = (
            scoped_logs.values(date=TruncDate("sent_at"))
            .annotate(
                sent=Count("id", filter=Q(status="sent")),
                failed=Count("id", filter=Q(status="failed")),
            )
            .order_by("date")
        )

        college_rows = (
            Contact.objects.filter(is_valid=True)
            .exclude(college__isnull=True)
            .exclude(college="")
            .values("college")
            .annotate(count=Count("id"))
            .order_by("-count")[:15]
        )

        status_distribution = (
            Contact.objects.filter(is_valid=True)
            .values("email_status")
            .annotate(count=Count("id"))
            .order_by("email_status")
        )

        return Response(
            {
                "kpi": {
                    "total_contacts": total_contacts,
                    "total_campaigns": total_campaigns,
                    "emails_sent": sent_count,
                    "emails_failed": failed_count,
                    "emails_pending": pending_count,
                    "success_rate": success_rate,
                    "delivery_rate": delivery_rate,
                    "today_sent": base_logs.filter(status="sent", sent_at__date=timezone.now().date()).count(),
                },
                "status_distribution": {item["email_status"]: item["count"] for item in status_distribution},
                "daily_trend": [
                    {
                        "date": row["date"].isoformat() if row["date"] else "",
                        "sent": row["sent"],
                        "failed": row["failed"],
                    }
                    for row in daily_trend_rows
                ],
                "campaign_performance": list(
                    Campaign.objects.values("name", sent=Count("email_logs", filter=Q(email_logs__status="sent")), failed=Count("email_logs", filter=Q(email_logs__status="failed")))
                    .order_by("-created_at")[:10]
                ),
                "college_distribution": {row["college"]: row["count"] for row in college_rows},
                "best_template": Campaign.objects.values("template__name").annotate(usage_count=Count("id")).order_by("-usage_count").first(),
            },
            status=status.HTTP_200_OK,
        )


class AnalyticsHeatmapView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date = timezone.now().date() - timedelta(days=30)
        rows = (
            EmailLog.objects.filter(sent_at__date__gte=start_date)
            .annotate(day=ExtractWeekDay("sent_at"), hour=ExtractHour("sent_at"))
            .values("day", "hour")
            .annotate(count=Count("id"))
        )
        return Response(
            {
                "heatmap": [
                    {
                        "day": row["day"] - 1 if row["day"] else 0,
                        "hour": row["hour"],
                        "count": row["count"],
                    }
                    for row in rows
                ]
            },
            status=status.HTTP_200_OK,
        )


class AnalyticsLogsView(generics.ListAPIView):
    serializer_class = EmailLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = EmailLog.objects.select_related("campaign", "contact").all().order_by("-sent_at")

        status_filter = self.request.query_params.get("status")
        campaign_id = self.request.query_params.get("campaign")
        search = self.request.query_params.get("search")

        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if campaign_id:
            queryset = queryset.filter(campaign_id=campaign_id)
        if search:
            queryset = queryset.filter(
                Q(recipient_email__icontains=search)
                | Q(campaign__name__icontains=search)
                | Q(contact__name__icontains=search)
            )
        return queryset


class AnalyticsLogsExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = EmailLog.objects.select_related("campaign", "contact").all().order_by("-sent_at")
        status_filter = request.query_params.get("status")
        campaign_id = request.query_params.get("campaign")
        search = request.query_params.get("search")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if campaign_id:
            queryset = queryset.filter(campaign_id=campaign_id)
        if search:
            queryset = queryset.filter(
                Q(recipient_email__icontains=search)
                | Q(campaign__name__icontains=search)
                | Q(contact__name__icontains=search)
            )

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="email_logs.csv"'

        import csv

        writer = csv.writer(response)
        writer.writerow(["Campaign", "Recipient", "Status", "Error", "Provider", "Sent At"])
        for log in queryset.iterator(chunk_size=1000):
            writer.writerow(
                [
                    log.campaign.name if log.campaign else "",
                    log.recipient_email,
                    log.status,
                    log.error_message,
                    log.provider_response,
                    log.sent_at.isoformat() if log.sent_at else "",
                ]
            )

        return response
