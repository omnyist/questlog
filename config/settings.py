from __future__ import annotations

import re
import sys
from pathlib import Path

import environ
import sentry_sdk
from sentry_sdk.scrubber import DEFAULT_DENYLIST
from sentry_sdk.scrubber import EventScrubber

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


# Secrets embedded in URL query strings (e.g. the Steam API key). The
# EventScrubber redacts dict params, but httpx bakes the full URL into
# HTTPStatusError text, which lands in the exception value as a plain string.
_URL_SECRET_RE = re.compile(
    r"([?&](?:key|api_key|apikey|token|secret|password)=)[^&\s\"']+",
    re.IGNORECASE,
)


def _sentry_before_send(event, hint):
    """Drop noise and redact URL secrets before sending.

    Drops: DisallowedHost scans, and interactive-shell tracebacks — the prod
    container runs DEBUG=False, so `manage.py shell` / piped REPL sessions have
    Sentry's excepthook active and typos there shouldn't page. Those frames
    have filename "<stdin>"; real server/Celery/command stacks never do.

    Redacts: secrets in URL query strings from exception messages.
    """
    if event.get("logger") == "django.security.DisallowedHost":
        return None
    for exc in event.get("exception", {}).get("values", []):
        frames = (exc.get("stacktrace") or {}).get("frames") or []
        if any(f.get("filename") == "<stdin>" for f in frames):
            return None
        if exc.get("value"):
            exc["value"] = _URL_SECRET_RE.sub(r"\1[Filtered]", exc["value"])
    return event


# Sentry (production only)
if not DEBUG:
    sentry_sdk.init(
        dsn=env("SENTRY_DSN", default=""),
        environment="production",
        send_default_pii=True,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        # Scrub secrets out of captured locals/request data. The default
        # denylist misses bare "key" (e.g. the Steam API key in request
        # params), and recursive descends into nested dicts like httpx params.
        event_scrubber=EventScrubber(
            denylist=[*DEFAULT_DENYLIST, "key"],
            recursive=True,
            send_default_pii=True,
        ),
        before_send=_sentry_before_send,
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
# Connection pooling in production only. Under pytest the pool's background
# worker thread holds connections across the test transaction and can wedge
# teardown, so leave it off for tests (and for SQLite, which rejects it).
_UNDER_TEST = "pytest" in sys.modules


def production_database_extras(engine: str, *, under_test: bool) -> dict:
    """The DB config that ships to production — pure, so tests can see it.

    Because the pool is off under pytest, everything in the production branch
    is invisible to an ordinary test run: a fully green suite shipped a
    crash-loop on 2026-08-22 (a `check` key colliding with the one Django
    passes itself). tests/test_production_db_config.py asserts on this
    function's output with under_test=False, which is the only way the shipped
    branch gets looked at before prod does.

    CONN_HEALTH_CHECKS does more than its name suggests: Django's postgresql
    backend forwards it to psycopg_pool as the pool's `check` callback. Left
    False, the pool validates nothing and serves connections killed by a
    Postgres restart forever (the 2026-08-21 shared-Postgres restart).

    Never put `check` in the pool options yourself — Django passes it, and
    psycopg_pool rejects the duplicate on the first cursor.
    """
    if engine == "django.db.backends.sqlite3" or under_test:
        return {}
    return {
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {"pool": True},
    }


DATABASES["default"].update(
    production_database_extras(DATABASES["default"]["ENGINE"], under_test=_UNDER_TEST)
)

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
