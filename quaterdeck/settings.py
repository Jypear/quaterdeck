"""
Django settings for Quaterdeck.

Reads configuration from environment variables (loaded from .env).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = os.environ.get("DEBUG", "False") == "True"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost").split(",")

# Django checks Origin against this, not ALLOWED_HOSTS — required for any
# production host (e.g. https://quaterdeck.example.com,http://192.168.1.50:8000).
CSRF_TRUSTED_ORIGINS = [origin for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if origin]

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "django_prometheus",
    # Local
    "core",
    "budget",
    "projects",
    "tasks",
    "notes",
    "webhooks",
]

MIDDLEWARE = [
    # Must be first so it starts the request timer before anything else runs.
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Quaterdeck: gates the whole app when REQUIRE_LOGIN is enabled
    "core.middleware.RequireLoginMiddleware",
    # Quaterdeck: OOB-renders queued messages into htmx partials (issue #13).
    # Must sit below MessageMiddleware so it marks messages used before
    # MessageMiddleware.process_response decides what to persist.
    "core.middleware.HtmxMessagesMiddleware",
    # Must be last so it wraps (and times) the fully-processed response.
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "quaterdeck.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

WSGI_APPLICATION = "quaterdeck.wsgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django_prometheus.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "quaterdeck"),
        "USER": os.environ.get("DB_USER", "quaterdeck"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/auth/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/auth/login/"

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        # Manifest storage requires collectstatic to have run, which local
        # runserver/test don't do — only use it in production (DEBUG=False).
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# ---------------------------------------------------------------------------
# Default primary key
# ---------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}
