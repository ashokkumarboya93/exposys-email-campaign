from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.contacts import views

router = DefaultRouter(trailing_slash="/?")
router.register(r"", views.ContactViewSet, basename="contact")

urlpatterns = [
    path("upload", views.FileUploadView.as_view(), name="contact-upload-no-slash"),
    path("upload/", views.FileUploadView.as_view(), name="contact-upload"),
    path("upload/<uuid:file_id>/progress", views.UploadedFileProgressView.as_view(), name="contact-upload-progress-no-slash"),
    path("upload/<uuid:file_id>/progress/", views.UploadedFileProgressView.as_view(), name="contact-upload-progress"),
    path("upload-status/<uuid:pk>", views.UploadedFileStatusView.as_view(), name="contact-upload-status-no-slash"),
    path("upload-status/<uuid:pk>/", views.UploadedFileStatusView.as_view(), name="contact-upload-status"),
    path("export", views.ContactExportView.as_view(), name="contact-export-no-slash"),
    path("export/", views.ContactExportView.as_view(), name="contact-export"),
    path("colleges", views.CollegeListView.as_view(), name="contact-colleges-no-slash"),
    path("colleges/", views.CollegeListView.as_view(), name="contact-colleges"),
    path("count", views.ContactCountView.as_view(), name="contact-count-no-slash"),
    path("count/", views.ContactCountView.as_view(), name="contact-count"),
    path("bulk-action", views.BulkContactActionView.as_view(), name="contacts-bulk-action-no-slash"),
    path("bulk-action/", views.BulkContactActionView.as_view(), name="contacts-bulk-action"),
    path("", include(router.urls)),
]
