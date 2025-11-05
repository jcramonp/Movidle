from pathlib import Path
import os
from dotenv import load_dotenv
import dj_database_url

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Cargar .env antes de leer variables ---
load_dotenv()

# --- Core / env ---
def _is_true(v: str) -> bool:
    return str(v).lower() in {"1", "true", "yes", "on"}

DEBUG = _is_true(os.getenv("DEBUG", "0"))
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")

_default_hosts = "localhost,127.0.0.1"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", _default_hosts).split(",") if h.strip()]

# --- Seguridad/Proxy ---
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')  # detrás de nginx
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# Para CSRF en admin/formularios cuando accedas por dominio/IP
CSRF_TRUSTED_ORIGINS = (
    [f"http://{h}" for h in ALLOWED_HOSTS if h not in {"localhost","127.0.0.1"}] +
    [f"https://{h}" for h in ALLOWED_HOSTS if h not in {"localhost","127.0.0.1"}]
)

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

OMDB_API_KEY = os.getenv("OMDB_API_KEY", "")

# --- Apps ---
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "moviegame.apps.MoviegameConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "movidle.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "django.template.context_processors.i18n",
    ]},
}]

WSGI_APPLICATION = "movidle.wsgi.application"

# --- DB ---
DATABASES = {
    "default": dj_database_url.config(conn_max_age=600, ssl_require=False)
}

# --- Passwords ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- i18n ---
LANGUAGE_CODE = "es"
USE_I18N = True
LANGUAGES = [("es", "Español"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]

# --- Static/Media ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
# Usa esta línea solo si tienes carpeta local "static/"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
