from .base import *
from urllib.parse import urlparse
from decouple import config

DEBUG = False

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
]

CORS_ALLOWED_ORIGIN_REGEXES = [
    r'^https://.*\.vercel\.app$',
]

CORS_ALLOW_CREDENTIALS = True

# Whitenoise — insert after SecurityMiddleware (index 0), before CorsMiddleware
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
