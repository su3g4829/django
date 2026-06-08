"""`store` 專案的 Django 設定檔。

這個專案雖然仍以本地 JSON 作為主要業務資料來源，
但設定層已補上接近正式環境需要的基礎設施，例如：
- 環境變數化設定
- 安全 cookie / proxy 設定
- cache-based rate limiting
- access log 與 health check
"""

from pathlib import Path
import os
import sys


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = BASE_DIR / "store" / ".env"


def _load_env_file(env_path: Path) -> None:
    """從本機 `.env` 載入環境變數。

    這裡不用額外安裝 `python-dotenv`，直接以最小需求解析 `KEY=VALUE` 格式。
    若同名環境變數已存在，保留既有值，不覆蓋 shell / CI 已注入的設定。
    """
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env_file(ENV_FILE_PATH)


def _env_bool(name: str, default: bool = False) -> bool:
    """把環境變數轉成布林值。"""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: list[str] | None = None) -> list[str]:
    """把逗號分隔的環境變數轉成字串列表。"""
    raw = os.getenv(name, "")
    items = [item.strip() for item in raw.split(",") if item.strip()]
    return items or list(default or [])


def _env_text(name: str) -> str:
    value = os.getenv(name, "")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _mysql_ssl_options() -> dict[str, object]:
    mode = _env_text("MYSQL_SSL_MODE").strip().upper()
    ca_path = _env_text("MYSQL_SSL_CA_PATH").strip()
    ca_cert = _env_text("MYSQL_SSL_CA_CERT").strip()

    if not mode and not ca_path and not ca_cert:
        return {}

    ssl_options: dict[str, str] = {}
    if ca_path:
        ssl_options["ca"] = ca_path
    elif ca_cert:
        cert_dir = BASE_DIR / "var" / "certs"
        cert_dir.mkdir(parents=True, exist_ok=True)
        cert_path = cert_dir / "mysql-ca.pem"
        normalized = ca_cert.replace("\\n", "\n").strip()
        cert_path.write_text(f"{normalized}\n", encoding="utf-8")
        ssl_options["ca"] = str(cert_path)

    if mode in {"REQUIRED", "VERIFY_CA", "VERIFY_IDENTITY", "VERIFY_FULL"}:
        return {"ssl": ssl_options if ssl_options else {}}
    return {}


APP_ENV = os.getenv("STORE_ENV", "development").strip().lower()
TESTING = "test" in sys.argv
DEBUG = _env_bool("DJANGO_DEBUG", APP_ENV == "development")

# 正式環境一定要由環境變數提供密鑰；開發 / 測試才允許 fallback。
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG or TESTING:
        SECRET_KEY = "django-insecure-local-dev-key"
    else:
        raise RuntimeError("DJANGO_SECRET_KEY must be set when DEBUG is disabled.")

ALLOWED_HOSTS = _env_list(
    "DJANGO_ALLOWED_HOSTS",
    default=["127.0.0.1", "localhost", "testserver", "f96c-36-225-169-2.ngrok-free.app"],
)
CSRF_TRUSTED_ORIGINS = _env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=["https://f96c-36-225-169-2.ngrok-free.app"],
)
FRONTEND_ORIGIN = os.getenv("STORE_FRONTEND_ORIGIN", "http://localhost:3000").rstrip("/")



# Django 內建與第三方 app 註冊清單。
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "myapp",
]

# Request 進入 view 前會依序經過這些 middleware。
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "myapp.middleware.RequestContextMiddleware",
    "myapp.middleware.RateLimitMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "store.urls"

# Django template engine 設定。
# `DIRS` 指向專案級 templates 資料夾；
# `context_processors` 會把常用變數自動注入所有模板。
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "myapp.context_processors.cart_summary",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "store.wsgi.application"
AUTH_USER_MODEL = "myapp.AppUser"

# 目前業務資料主要不走資料庫，但仍保留 Django 內建元件可用的 SQLite。
DB_BACKEND  = os.getenv("STORE_DB_BACKEND", "sqlite").strip().lower()

if DB_BACKEND == "mysql":
    mysql_options: dict[str, object] = {
        "charset": "utf8mb4",
    }
    mysql_options.update(_mysql_ssl_options())
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("MYSQL_DATABASE", "store_db"),
            "USER": os.getenv("MYSQL_USER", "store_user"),
            "PASSWORD": os.getenv("MYSQL_PASSWORD", ""),
            "HOST": os.getenv("MYSQL_HOST", "127.0.0.1"),
            "PORT": os.getenv("MYSQL_PORT", "3306"),
            "OPTIONS": mysql_options,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# 這些驗證器主要對 Django 內建 auth 生效；
# 本專案的 demo auth 也可把它們當作密碼規則參考。
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


LANGUAGE_CODE = "zh-Hant"
TIME_ZONE = "Asia/Taipei"
USE_I18N = True
USE_TZ = True


# 靜態檔 / 媒體檔 / 運維資料夾設定。
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

OPS_DIR = BASE_DIR / "var"
CACHE_DIR = OPS_DIR / "cache"
LOG_DIR = OPS_DIR / "log"
for directory in (STATIC_ROOT, MEDIA_ROOT, CACHE_DIR, LOG_DIR):
    directory.mkdir(parents=True, exist_ok=True)


# 使用 signed cookie session，讓專案在不依賴 session table 的情況下也能保存登入與購物車。
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE", str(60 * 60 * 24 * 14)))
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = _env_bool("CSRF_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_HTTPONLY = _env_bool("CSRF_COOKIE_HTTPONLY", False)
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")

# 反向代理與安全 header 設定。
SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = os.getenv("SECURE_REFERRER_POLICY", "same-origin")
SECURE_CROSS_ORIGIN_OPENER_POLICY = os.getenv("SECURE_CROSS_ORIGIN_OPENER_POLICY", "same-origin")
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0" if DEBUG else "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = _env_bool("SECURE_HSTS_PRELOAD", False)
X_FRAME_OPTIONS = os.getenv("X_FRAME_OPTIONS", "DENY")
USE_X_FORWARDED_HOST = _env_bool("USE_X_FORWARDED_HOST", False)
if _env_bool("TRUST_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
WHITENOISE_MAX_AGE = int(os.getenv("WHITENOISE_MAX_AGE", "31536000" if not DEBUG else "0"))

# 上傳檔大小限制，避免單次請求佔用過多記憶體。
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv("DATA_UPLOAD_MAX_MEMORY_SIZE", str(5 * 1024 * 1024)))
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv("FILE_UPLOAD_MAX_MEMORY_SIZE", str(5 * 1024 * 1024)))


# Cache 目前支援 locmem 與 filebased 兩種 backend。
# 未來若導入 Redis，可從這裡切換。
CACHE_BACKEND = os.getenv("STORE_CACHE_BACKEND", "locmem").strip().lower()
if CACHE_BACKEND == "filebased":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
            "LOCATION": str(CACHE_DIR),
            "TIMEOUT": int(os.getenv("STORE_CACHE_TIMEOUT", "300")),
            "OPTIONS": {"MAX_ENTRIES": int(os.getenv("STORE_CACHE_MAX_ENTRIES", "1000"))},
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": os.getenv("STORE_CACHE_LOCATION", "store-demo-cache"),
            "TIMEOUT": int(os.getenv("STORE_CACHE_TIMEOUT", "300")),
        }
    }


# request id / access log / rate limit 設定。
REQUEST_ID_HEADER = "X-Request-ID"
ACCESS_LOG_ENABLED = _env_bool("STORE_ACCESS_LOG_ENABLED", True)
RATE_LIMIT_ENABLED = _env_bool("STORE_RATE_LIMIT_ENABLED", not TESTING)
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("STORE_RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_AUTH_LIMIT = int(os.getenv("STORE_RATE_LIMIT_AUTH_LIMIT", "30"))
RATE_LIMIT_WRITE_LIMIT = int(os.getenv("STORE_RATE_LIMIT_WRITE_LIMIT", "240"))


# DRF 與 OpenAPI 文件設定。
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Store Demo API",
    "DESCRIPTION": "JSON-backed prototype API built with Django REST Framework without relying on database models.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}


# logging 設定：分成一般應用 log 與 access log。
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "application_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "application.log"),
            "maxBytes": 2 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "standard",
            "encoding": "utf-8",
        },
        "access_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "access.log"),
            "maxBytes": 2 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "standard",
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console", "application_file"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
        },
        "store": {
            "handlers": ["console", "application_file"],
            "level": os.getenv("STORE_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "store.access": {
            "handlers": ["access_file", "console"],
            "level": os.getenv("STORE_ACCESS_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}
