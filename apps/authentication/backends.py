from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.models import AdminUser


class JWTAuthBackend(JWTAuthentication):
    """
    Custom JWT authentication backend that authenticates against
    the AdminUser model instead of Django's built-in User model.
    """

    def get_user(self, validated_token):
        """
        Look up the AdminUser from the validated JWT token's user_id claim.
        Raises AuthenticationFailed if user is not found or inactive.
        """
        try:
            user_id = validated_token['user_id']
        except KeyError:
            raise InvalidToken({
                'detail': 'Token contained no recognizable user identification.',
            })

        try:
            user = AdminUser.objects.get(id=user_id)
        except AdminUser.DoesNotExist:
            raise AuthenticationFailed({
                'detail': 'User not found.',
                'code': 'user_not_found',
            })

        if not user.is_active:
            raise AuthenticationFailed({
                'detail': 'User account is disabled.',
                'code': 'user_inactive',
            })

        return user


def get_tokens_for_user(user):
    """
    Generate a JWT access/refresh token pair for the given AdminUser.
    Embeds user_id, email, and role as custom claims.
    """
    refresh = RefreshToken()
    refresh['user_id'] = str(user.id)
    refresh['email'] = user.email
    refresh['role'] = user.role

    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
    }
