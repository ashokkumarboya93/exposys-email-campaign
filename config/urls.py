"""Root URL configuration for Exposys Email Campaign."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView, TemplateView
from django.views.static import serve
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

from apps.authentication.views import SettingsView
from apps.campaigns.views import TaskStatusView

schema_view = get_schema_view(
    openapi.Info(
        title="Exposys Email Campaign API",
        default_version="v1",
        description=(
            "Multi-tenant email campaign automation platform. "
            "Provides contact management, template rendering, "
            "batch email sending, and analytics."
        ),
        contact=openapi.Contact(email="admin@exposys.com"),
        license=openapi.License(name="Proprietary"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    path("", RedirectView.as_view(url="/dashboard/")),
    path("login/", TemplateView.as_view(template_name="login.html")),
    path("dashboard/", TemplateView.as_view(template_name="dashboard.html")),
    path("upload/", TemplateView.as_view(template_name="upload.html")),
    path("preview/", TemplateView.as_view(template_name="preview.html")),
    path("contacts/", TemplateView.as_view(template_name="contacts.html")),
    path("templates/", TemplateView.as_view(template_name="template_builder.html")),
    path("campaigns/", TemplateView.as_view(template_name="campaign.html")),
    path("analytics/", TemplateView.as_view(template_name="analytics.html")),
    path("history/", TemplateView.as_view(template_name="history.html")),
    path("logs/", TemplateView.as_view(template_name="logs.html")),
    path("settings/", TemplateView.as_view(template_name="settings.html")),
    path("admin/", admin.site.urls),
    re_path(r"^api/auth(?:/|$)", include("apps.authentication.urls")),
    re_path(r"^api/contacts(?:/|$)", include("apps.contacts.urls")),
    re_path(r"^api/templates(?:/|$)", include("apps.templates_engine.urls")),
    re_path(r"^api/campaigns(?:/|$)", include("apps.campaigns.urls")),
    re_path(r"^api/analytics(?:/|$)", include("apps.analytics.urls")),
    path("api/settings/", SettingsView.as_view(), name="api-settings"),
    path("api/tasks/<str:task_id>/status/", TaskStatusView.as_view(), name="task-status"),
    path("swagger/", schema_view.with_ui("swagger", cache_timeout=0), name="schema-swagger-ui"),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
    path("swagger.json", schema_view.without_ui(cache_timeout=0), name="schema-json"),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += [
    re_path(
        r"^static/(?P<path>.*)$",
        serve,
        {"document_root": settings.BASE_DIR / "static"},
    )
]
