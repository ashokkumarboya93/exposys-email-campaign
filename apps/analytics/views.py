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


class CampaignAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, campaign_id):
        try:
            campaign = Campaign.objects.get(id=campaign_id)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found"}, status=status.HTTP_404_NOT_FOUND)

        from apps.campaigns.models import CampaignContact
        from apps.analytics.models import EmailDeliveryStatus, EmailEvent

        contacts = CampaignContact.objects.filter(campaign=campaign).select_related('contact', 'delivery_status_record')
        
        # Aggregate counts
        counts = {
            "sent": 0,
            "delivered": 0,
            "opened": 0,
            "clicked": 0,
            "bounced": 0,
            "failed": 0,
            "unsubscribed": 0,
            "unknown": 0,
            "pending": 0,
            "limit_reached": 0,
        }
        
        recipient_data = []
        for cc in contacts:
            cc_status = cc.delivery_status_record.status if hasattr(cc, 'delivery_status_record') else cc.delivery_status
            
            # Intercept Rate Limit logic based on last error
            if cc_status == "failed" and cc.last_error_message and "Rate limit" in str(cc.last_error_message):
                cc_status = "limit_reached"
                
            if cc_status in counts:
                counts[cc_status] += 1
            elif cc_status == "retrying":
                counts["failed"] += 1
                
            recipient_data.append({
                "campaign_contact_id": cc.id,
                "email": cc.contact.email,
                "name": cc.contact.name,
                "status": cc_status,
                "last_error": cc.last_error_message,
            })
            
        # Get historical events for this campaign
        events = EmailEvent.objects.filter(campaign_contact__campaign=campaign).order_by('created_at')
        
        # Build trends (very basic aggregation by day)
        daily_opens = {}
        daily_clicks = {}
        
        for e in events:
            day = e.created_at.date().isoformat()
            if e.event_type == "opened":
                daily_opens[day] = daily_opens.get(day, 0) + 1
            elif e.event_type == "clicked":
                daily_clicks[day] = daily_clicks.get(day, 0) + 1
                
        trend_labels = sorted(list(set(list(daily_opens.keys()) + list(daily_clicks.keys()))))
        open_trend = [daily_opens.get(d, 0) for d in trend_labels]
        click_trend = [daily_clicks.get(d, 0) for d in trend_labels]

        return Response({
            "campaign_id": campaign.id,
            "name": campaign.name,
            "counts": counts,
            "recipients": recipient_data,
            "trends": {
                "labels": trend_labels,
                "opens": open_trend,
                "clicks": click_trend
            }
        })

class RecipientEventHistoryView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, campaign_contact_id):
        from apps.analytics.models import EmailEvent
        events = EmailEvent.objects.filter(campaign_contact_id=campaign_contact_id).order_by('-created_at')
        data = []
        for e in events:
            data.append({
                "event_type": e.event_type,
                "created_at": e.created_at.isoformat(),
                "ip_address": e.ip_address,
                "user_agent": e.user_agent,
            })
        return Response({"history": data})


import base64
import json
from django.shortcuts import redirect
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from apps.analytics.tasks import process_tracking_event

class TrackOpenView(View):
    def get(self, request, uuid):
        pixel = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
        
        ip = request.META.get('REMOTE_ADDR')
        user_agent = request.META.get('HTTP_USER_AGENT')
        process_tracking_event.delay(str(uuid), "opened", ip, user_agent, {})
        
        response = HttpResponse(pixel, content_type="image/gif")
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        return response

class TrackClickView(View):
    def get(self, request, uuid):
        url = request.GET.get("url")
        if url:
            ip = request.META.get('REMOTE_ADDR')
            user_agent = request.META.get('HTTP_USER_AGENT')
            process_tracking_event.delay(str(uuid), "clicked", ip, user_agent, {"url": url})
            return redirect(url)
        return HttpResponse(status=400)

@method_decorator(csrf_exempt, name='dispatch')
class WebhookBrevoView(View):
    def post(self, request):
        try:
            payload = json.loads(request.body)
            event = payload.get("event")
            
            cc_id = payload.get("tags", [None])[0] if payload.get("tags") else None
            
            event_mapping = {
                "delivered": "delivered",
                "hard_bounce": "bounced",
                "soft_bounce": "bounced",
                "complaint": "failed",
                "unsubscribed": "unsubscribed",
            }
            mapped_event = event_mapping.get(event)
            
            if cc_id and mapped_event:
                process_tracking_event.delay(str(cc_id), mapped_event, None, None, payload)
            
            return HttpResponse("OK", status=200)
        except Exception:
            return HttpResponse("Error", status=400)

@method_decorator(csrf_exempt, name='dispatch')
class WebhookSesView(View):
    def post(self, request):
        try:
            payload = json.loads(request.body)
            if payload.get("Type") == "SubscriptionConfirmation":
                return HttpResponse("OK", status=200)
            
            msg = json.loads(payload.get("Message", "{}"))
            notification_type = msg.get("notificationType")
            
            tags = msg.get("mail", {}).get("tags", {})
            cc_id = tags.get("campaign_contact_id", [None])[0]
            
            event_mapping = {
                "Delivery": "delivered",
                "Bounce": "bounced",
                "Complaint": "failed",
            }
            mapped_event = event_mapping.get(notification_type)
            
            if cc_id and mapped_event:
                process_tracking_event.delay(str(cc_id), mapped_event, None, None, msg)
            
            return HttpResponse("OK", status=200)
        except Exception:
            return HttpResponse("Error", status=400)
