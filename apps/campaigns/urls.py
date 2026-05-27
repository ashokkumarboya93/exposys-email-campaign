from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.campaigns import views

router = DefaultRouter(trailing_slash="/?")
router.register(r"", views.CampaignViewSet, basename="campaign")

urlpatterns = [
    path("<uuid:pk>/launch/", views.CampaignLaunchView.as_view(), name="campaign-launch"),
    path("<uuid:pk>/pause/", views.CampaignPauseView.as_view(), name="campaign-pause"),
    path("<uuid:pk>/resume/", views.CampaignResumeView.as_view(), name="campaign-resume"),
    path("<uuid:pk>/retry/", views.CampaignRetryView.as_view(), name="campaign-retry"),
    path("<uuid:pk>/status/", views.CampaignStatusView.as_view(), name="campaign-status"),
    path("<uuid:pk>/logs/", views.CampaignLogsView.as_view(), name="campaign-logs"),
    path("<uuid:pk>/contacts/", views.CampaignContactsAddView.as_view(), name="campaign-contacts-add"),
    path("logs/export/", views.EmailLogsExportView.as_view(), name="logs-export"),
    path("", include(router.urls)),
]
