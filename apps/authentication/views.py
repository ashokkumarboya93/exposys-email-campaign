import logging
import uuid

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.backends import get_tokens_for_user
from apps.authentication.models import SystemSettings
from apps.authentication.serializers import (
    ForgotPasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    UserProfileSerializer,
)

logger = logging.getLogger(__name__)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data["user"]
        tokens = get_tokens_for_user(user)

        return Response(
            {
                "access": tokens["access"],
                "refresh": tokens["refresh"],
                "user": UserProfileSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            token.blacklist()
        except TokenError as exc:
            return Response({"detail": str(exc), "code": "token_error"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "Successfully logged out."}, status=status.HTTP_205_RESET_CONTENT)


class RefreshTokenView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "Refresh token is required.", "code": "missing_token"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            old_refresh = RefreshToken(refresh_token)
            new_refresh = RefreshToken()
            new_refresh["user_id"] = old_refresh["user_id"]
            new_refresh["email"] = old_refresh["email"]
            new_refresh["role"] = old_refresh["role"]
            old_refresh.blacklist()
        except TokenError as exc:
            return Response({"detail": str(exc), "code": "token_error"}, status=status.HTTP_401_UNAUTHORIZED)

        return Response(
            {
                "access": str(new_refresh.access_token),
                "refresh": str(new_refresh),
            },
            status=status.HTTP_200_OK,
        )


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        reset_token = str(uuid.uuid4())
        logger.info("Password reset requested for %s token=%s", email, reset_token)

        return Response({"message": "Password reset link sent to email."}, status=status.HTTP_200_OK)


class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        system = SystemSettings.get_solo()

        return Response(
            {
                "provider": system.email_provider,
                "aws_settings": system.ses_config,
                "brevo_settings": system.brevo_config,
                "campaign_defaults": system.campaign_defaults or {
                    "batch_size": 50,
                    "batch_delay_seconds": 2,
                    "max_retries": 2,
                    "brevo_max_concurrent": 30,
                    "ses_max_concurrent": 14,
                },
                "notification_preferences": system.notification_preferences or {
                    "email_on_completion": True,
                    "alert_on_high_failure": True,
                    "daily_summary": False,
                },
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        system = SystemSettings.get_solo()
        data = request.data

        profile = data.get("profile")
        if profile and profile.get("new_password"):
            user = request.user
            current_password = profile.get("current_password")
            if user.check_password(current_password):
                user.set_password(profile["new_password"])
                user.save(update_fields=["password_hash"])
            else:
                return Response({"error": "Incorrect current password"}, status=status.HTTP_400_BAD_REQUEST)

        if data.get("provider") in {"brevo", "ses"}:
            system.email_provider = data["provider"]

        if "aws_settings" in data and isinstance(data["aws_settings"], dict):
            system.ses_config = data["aws_settings"]

        if "brevo_settings" in data and isinstance(data["brevo_settings"], dict):
            system.brevo_config = data["brevo_settings"]

        if "campaign_defaults" in data and isinstance(data["campaign_defaults"], dict):
            system.campaign_defaults = data["campaign_defaults"]

        if "notification_preferences" in data and isinstance(data["notification_preferences"], dict):
            system.notification_preferences = data["notification_preferences"]

        system.save()
        return Response({"message": "Settings updated successfully"}, status=status.HTTP_200_OK)
