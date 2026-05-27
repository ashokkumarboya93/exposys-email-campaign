from django.utils import timezone
from rest_framework import serializers

from apps.authentication.models import AdminUser


class LoginSerializer(serializers.Serializer):
    """Validates login credentials and returns the authenticated user."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        try:
            user = AdminUser.objects.get(email=email)
        except AdminUser.DoesNotExist:
            raise serializers.ValidationError({
                'detail': 'Invalid email or password.',
                'code': 'invalid_credentials',
            })

        if not user.check_password(password):
            raise serializers.ValidationError({
                'detail': 'Invalid email or password.',
                'code': 'invalid_credentials',
            })

        if not user.is_active:
            raise serializers.ValidationError({
                'detail': 'User account is disabled.',
                'code': 'user_inactive',
            })

        # Update last_login timestamp
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])

        attrs['user'] = user
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    """Read-only serializer for AdminUser profile data."""

    class Meta:
        model = AdminUser
        fields = [
            'id',
            'email',
            'full_name',
            'role',
            'is_active',
            'last_login',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class ForgotPasswordSerializer(serializers.Serializer):
    """Validates the email for password reset requests."""

    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            AdminUser.objects.get(email=value)
        except AdminUser.DoesNotExist:
            raise serializers.ValidationError(
                'No account found with this email address.'
            )
        return value


class LogoutSerializer(serializers.Serializer):
    """Accepts a refresh token for blacklisting on logout."""

    refresh = serializers.CharField()
