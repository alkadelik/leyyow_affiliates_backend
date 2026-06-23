from .base import *
from urllib.parse import urlparse
from decouple import config

DEBUG = config('DEBUG')

ALLOWED_HOSTS = ['leyyowaffiliatesbackend-production.up.railway.app']

_db = urlparse(config('DATABASE_URL'))
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': _db.path[1:],
        'USER': _db.username,
        'PASSWORD': _db.password,
        'HOST': _db.hostname,
        'PORT': _db.port or 5432,
    }
}

CSRF_TRUSTED_ORIGINS = [
    'https://leyyow-affiliates-admin-git-main-alkadeliks-projects.vercel.app',
    'https://leyyowaffiliatesbackend-production.up.railway.app',
    'https://leyyow-affiliates-admin.vercel.app',
    'https://leyyow-affiliates.vercel.app',
]

CORS_ALLOWED_ORIGINS = [
    'https://leyyow-affiliates-admin.vercel.app',
    'https://leyyow-affiliates.vercel.app',
    # 'http://localhost:3000',
]

# CORS_ALLOWED_ORIGIN_REGEXES = [
#     r'^https://.*\.vercel\.app$',
# ]

CORS_ALLOW_CREDENTIALS = True

AFFILIATE_FRONTEND_URL = config('AFFILIATE_FRONTEND_URL')

EMAIL_BACKEND = 'anymail.backends.resend.EmailBackend'
ANYMAIL = {
    'RESEND_API_KEY': config('RESEND_API_KEY'),
}

# Whitenoise — insert after SecurityMiddleware (index 0), before CorsMiddleware
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# HTTPS security headers
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('REDIS_URL'),
    }
}

