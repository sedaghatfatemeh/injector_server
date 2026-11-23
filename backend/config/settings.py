import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [host for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host]

INSTALLED_APPS = [
    "config.admin.SuperAdministratorAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "corsheaders",
    "devices",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "injector_server"),
        "USER": os.environ.get("POSTGRES_USER", "injector_server"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": int(os.environ.get("POSTGRES_CONN_MAX_AGE", "60")),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fa-ir"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))
MEDIA_URL = "/media/"

DEVICE_ONLINE_WINDOW_MINUTES = int(os.environ.get("DEVICE_ONLINE_WINDOW_MINUTES", "15"))
DEVICE_EVENT_BATCH_MAX = int(os.environ.get("DEVICE_EVENT_BATCH_MAX", "200"))
DEVICE_EVENT_BATCH_MAX_BYTES = int(os.environ.get("DEVICE_EVENT_BATCH_MAX_BYTES", str(2 * 1024 * 1024)))
DEVICE_EVENT_METADATA_MAX_DEPTH = int(os.environ.get("DEVICE_EVENT_METADATA_MAX_DEPTH", "8"))
DEVICE_EVENT_FUTURE_SKEW_SECONDS = int(os.environ.get("DEVICE_EVENT_FUTURE_SKEW_SECONDS", "300"))
DEVICE_CHECK_IN_MAX_BYTES = int(os.environ.get("DEVICE_CHECK_IN_MAX_BYTES", "4096"))
DEVICE_EVENT_METADATA_MAX_BYTES = int(os.environ.get("DEVICE_EVENT_METADATA_MAX_BYTES", "16384"))
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get("DATA_UPLOAD_MAX_MEMORY_SIZE", str(2 * 1024 * 1024)))
DEVICE_TOKEN_HEADER = "HTTP_AUTHORIZATION"
DEVICE_UPDATE_ROLLOUT_ENABLED = os.environ.get("DEVICE_UPDATE_ROLLOUT_ENABLED", "false").lower() == "true"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "devices.authentication.DeviceTokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "20/minute", "user": "240/minute", "login": os.environ.get("STAFF_LOGIN_RATE", "10/minute"),
        "device_check_in": os.environ.get("DEVICE_CHECK_IN_RATE", "60/minute"),
        "device_events": os.environ.get("DEVICE_EVENTS_RATE", "120/minute"),
        "device_manifest": os.environ.get("DEVICE_MANIFEST_RATE", "30/minute"),
        "device_update_result": os.environ.get("DEVICE_UPDATE_RESULT_RATE", "60/minute"),
    },
    # Trust forwarded client addresses only after the actual proxy chain is configured.
    "NUM_PROXIES": int(os.environ.get("API_NUM_PROXIES", "0")),
}

CORS_ALLOWED_ORIGINS = [origin for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if origin]
CORS_ALLOW_CREDENTIALS = True
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_AGE = int(os.environ.get("STAFF_SESSION_AGE_SECONDS", "28800"))
STAFF_SESSION_AGE_SECONDS = SESSION_COOKIE_AGE
CSRF_TRUSTED_ORIGINS = [origin for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if origin]
if not DEBUG and (not SECRET_KEY or SECRET_KEY.startswith("replace-with-")):
    raise ValueError("DJANGO_SECRET_KEY must be set to a private random value when DEBUG is false.")
if not DEBUG and (not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS):
    raise ValueError("DJANGO_ALLOWED_HOSTS must contain explicit hostnames when DEBUG is false.")
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
