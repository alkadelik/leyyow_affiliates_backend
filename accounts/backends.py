from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed
from accounts.models import Affiliate


class AffiliateJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication backend for affiliates.
    Looks up Affiliate model instead of AUTH_USER_MODEL (Admin).
    """
    def get_user(self, validated_token):
        try:
            user_id = validated_token['user_id']
            user_type = validated_token.get('user_type')
            jti = validated_token['jti']
        except KeyError:
            raise InvalidToken('Token contained no recognisable user identification')

        if user_type != 'affiliate':
            raise AuthenticationFailed('Token is not an affiliate token')

        # Check blacklist
        from accounts.models import AffiliateTokenBlacklist
        if AffiliateTokenBlacklist.objects.filter(token_jti=jti).exists():
            raise AuthenticationFailed('Token has been blacklisted')

        try:
            affiliate = Affiliate.objects.get(id=user_id)
        except Affiliate.DoesNotExist:
            raise AuthenticationFailed('Affiliate not found')

        if affiliate.status == 'deactivated':
            raise AuthenticationFailed('Affiliate account has been deactivated')

        return affiliate