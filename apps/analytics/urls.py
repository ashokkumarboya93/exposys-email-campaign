from django.urls import path

from apps.analytics import views

urlpatterns = [
    path("dashboard/", views.DashboardView.as_view(), name="analytics-dashboard"),
    path("heatmap/", views.AnalyticsHeatmapView.as_view(), name="analytics-heatmap"),
    path("logs/", views.AnalyticsLogsView.as_view(), name="analytics-logs"),
    path("logs/export/", views.AnalyticsLogsExportView.as_view(), name="analytics-logs-export"),
    
    # Tracking endpoints
    path("track/open/<uuid:uuid>/pixel.gif", views.TrackOpenView.as_view(), name="track-open"),
    path("track/click/<uuid:uuid>/", views.TrackClickView.as_view(), name="track-click"),
    
    # Webhooks
    path("webhooks/brevo/", views.WebhookBrevoView.as_view(), name="webhook-brevo"),
    path("webhooks/ses/", views.WebhookSesView.as_view(), name="webhook-ses"),
    
    # Detailed Analytics
    path("campaign/<uuid:campaign_id>/", views.CampaignAnalyticsView.as_view(), name="campaign-analytics"),
    path("recipient/<uuid:campaign_contact_id>/history/", views.RecipientEventHistoryView.as_view(), name="recipient-history"),
]
