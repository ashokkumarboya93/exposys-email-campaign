from django.urls import path

from apps.authentication import views

urlpatterns = [
    path('login/', views.LoginView.as_view(), name='auth-login'),
    path('logout/', views.LogoutView.as_view(), name='auth-logout'),
    path('refresh/', views.RefreshTokenView.as_view(), name='auth-refresh'),
    path('forgot-password/', views.ForgotPasswordView.as_view(), name='auth-forgot-password'),
    path('me/', views.UserProfileView.as_view(), name='auth-me'),
]
