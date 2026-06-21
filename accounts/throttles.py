from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

class AuthRateThrottle(AnonRateThrottle):
    scope = 'auth'

class PayoutRateThrottle(UserRateThrottle):
    scope = 'payout'

class TokenRefreshRateThrottle(AnonRateThrottle):
    scope = 'token_refresh'
