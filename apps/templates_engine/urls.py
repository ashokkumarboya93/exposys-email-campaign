from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.templates_engine import views

router = DefaultRouter(trailing_slash=False)
router.register(r'', views.EmailTemplateViewSet, basename='template')

urlpatterns = [
    path('<uuid:pk>/preview/', views.TemplatePreviewView.as_view(), name='template-preview'),
    path('', include(router.urls)),
]
