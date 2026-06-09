from pathlib import Path
from decouple import config
from urllib.parse import urlparse
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
AUTH_USER_MODEL = 'accounts.Admin'

SECRET_KEY = config('SECRET_KEY')
LEYYOW_INTERNAL_SECRET_KEY = config('LEYYOW_INTERNAL_SECRET_KEY', default='')

DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'b59c-102-88-55-231.ngrok-free.app', 'leyyowaffiliatesbackend-production.up.railway.app', '.vercel.app',]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'accounts',
    'audit',
    'campaigns',
    'tracking',
    'payouts',
    'analytics',
    'rest_framework_simplejwt.token_blacklist',
    'django_celery_results',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

CSRF_TRUSTED_ORIGINS = [
    "https://leyyow-affiliates-admin-git-main-alkadeliks-projects.vercel.app",
    "https://leyyowaffiliatesbackend-production.up.railway.app",
    "https://leyyow-affiliates-admin.vercel.app",
    "https://leyyow-affiliates.vercel.app",
]

CORS_ALLOWED_ORIGINS = [
    "https://leyyow-affiliates-admin.vercel.app",
    "https://leyyow-affiliates.vercel.app",
    "http://localhost:5173",
    "http://localhost:5174",
]

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.vercel\.app$",
]

CORS_ALLOW_CREDENTIALS = True

ROOT_URLCONF = 'affiliates_backend.urls'


TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'affiliates_backend.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

# DATABASE_URL = config('DATABASE_URL')
# if DATABASE_URL:
#     # For use on Railway
#     db = urlparse(DATABASE_URL)
#     DATABASES = {
#         'default': {
#             'ENGINE': 'django.db.backends.postgresql',
#             'NAME': db.path[1:],
#             'USER': db.username,
#             'PASSWORD': db.password,
#             'HOST': db.hostname,
#             'PORT': db.port or 5432,
#         }
#     }
# else:
#     DATABASES = {
#         'default': {
#             # 'ENGINE': 'django.db.backends.sqlite3',
#             # 'NAME': BASE_DIR / 'db.sqlite3',
#             'ENGINE': 'django.db.backends.postgresql',
#             'NAME': 'leyyow_affiliate',
#             'USER': 'postgres', # your postgres username
#             'PASSWORD': 'your_password',
#             'HOST': 'localhost',
#             'PORT': '5432',
#         }
#     }
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'leyyow_affiliate',
        'USER': 'postgres', # your postgres username
        'PASSWORD': 'your_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

PAYSTACK_SECRET_KEY = config('PAYSTACK_SECRET_KEY', default='')

ADMIN_FRONTEND_URL = config('ADMIN_FRONTEND_URL', default='http://localhost:5173')
AFFILIATE_FRONTEND_URL = config('AFFILIATE_FRONTEND_URL', default='http://localhost:5174')
TRACKING_BASE_URL = config('TRACKING_BASE_URL', default='http://localhost:8000')
CAMPAIGN_LANDING_URL = config('CAMPAIGN_LANDING_URL', default='https://leyyow.com')

# Email settings
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL')#, default='noreply@leyyow.com')
ADMIN_NOTIFICATION_EMAIL = config('ADMIN_NOTIFICATION_EMAIL', default='admin@leyyow.com')
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)

# Celery
CELERY_BROKER_URL = 'redis://127.0.0.1:6379/0'
CELERY_RESULT_BACKEND = 'django-db'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER  = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True

# MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
# STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'