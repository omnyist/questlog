from __future__ import annotations

import os
from pathlib import Path

import environ
import sentry_sdk

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, "insecure-dev-key-change-in-production"),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=["https://questlog.omnyist.com"])

# Sentry (production only)
if not DEBUG:
    sentry_sdk.init(
        dsn=env("SENTRY_DSN", default=""),
        environment="production",
        send_default_pii=True,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        before_send=lambda event, hint: event
        if event.get("logger") != "django.security.DisallowedHost"
        else None,
    )

# Application definition
INSTALLED_APPS = [
    "corsheaders",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local apps
    "apps.library",
    "apps.journal",
    "apps.lists",
    "apps.profiles.ffxiv",
    "apps.profiles.destiny",
    "apps.profiles.poe",
    "apps.profiles.umamusume",
    "apps.profiles.acnh",
    "apps.profiles.ironmon",
    "apps.profiles.warframe",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgresql://questlog:questlog@localhost:5433/questlog",
    ),
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Redis
REDIS_URL = env("REDIS_URL", default="redis://localhost:6380/0")

# Cache
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "questlog",
    }
}

# IGDB API (Twitch OAuth)
IGDB_CLIENT_ID = env("TWITCH_CLIENT_ID", default="")
IGDB_CLIENT_SECRET = env("TWITCH_CLIENT_SECRET", default="")
IGDB_RATE_LIMIT = 4  # requests per second (free tier limit)

# Bungie API
BUNGIE_API_KEY = env("BUNGIE_API_KEY", default="")
BUNGIE_RATE_LIMIT = 8  # requests per second (conservative vs ~25/sec observed)

# Steam API
STEAM_API_KEY = env("STEAM_API_KEY", default="")
STEAM_ID = env("STEAM_ID", default="")
STEAM_RATE_LIMIT = 4  # requests per second

# Warframe
WARFRAME_ACCOUNT_ID = env("WARFRAME_ACCOUNT_ID", default="")
WARFRAME_PLATFORM = env("WARFRAME_PLATFORM", default="pc")

# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True

# CORS
CORS_ALLOW_ALL_ORIGINS = True
CORS_URLS_REGEX = r"^/api/.*$"

# API Authentication
API_KEY = env("API_KEY", default="")
