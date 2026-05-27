from django.urls import path

from apps.analytics import views

urlpatterns = [
    path("dashboard/", views.DashboardView.as_view(), name="analytics-dashboard"),
    path("heatmap/", views.AnalyticsHeatmapView.as_view(), name="analytics-heatmap"),
    path("logs/", views.AnalyticsLogsView.as_view(), name="analytics-logs"),
    path("logs/export/", views.AnalyticsLogsExportView.as_view(), name="analytics-logs-export"),
]
