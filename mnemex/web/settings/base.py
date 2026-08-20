from __future__ import annotations

from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[3]

DEBUG = False
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "mnemex.accounts.apps.AccountsConfig",
    "mnemex.foundation.apps.FoundationConfig",
    "mnemex.partners.apps.PartnersConfig",
    "mnemex.people.apps.PeopleConfig",
    "mnemex.consent.apps.ConsentConfig",
    "mnemex.results.apps.ResultsConfig",
    "mnemex.legacy_migration.apps.LegacyMigrationConfig",
    "mnemex.career.apps.CareerConfig",
    "mnemex.export.apps.ExportConfig",
    "mnemex.activation.apps.ActivationConfig",
    "mnemex.recovery.apps.RecoveryConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "mnemex.accounts.middleware.PrivilegedAccountSecurityMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "mnemex.web.urls"
WSGI_APPLICATION = "mnemex.web.wsgi.application"
ASGI_APPLICATION = "mnemex.web.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "mnemex" / "accounts" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

AUTH_USER_MODEL = "accounts.Account"
AUTHENTICATION_BACKENDS = ["allauth.account.auth_backends.AuthenticationBackend"]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "results:dashboard"
LOGOUT_REDIRECT_URL = "account_login"

# MNEMEX owns an invite-only account experience while django-allauth supplies
# maintained email verification, password recovery, reauthentication, MFA, and
# abuse-control flows. Public self-service signup remains closed.
ACCOUNT_ADAPTER = "mnemex.accounts.adapters.MnemexAccountAdapter"
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_PREVENT_ENUMERATION = True
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_REAUTHENTICATION_TIMEOUT = 300
ACCOUNT_REAUTHENTICATION_REQUIRED = True
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = True
ACCOUNT_EMAIL_NOTIFICATIONS = True

MFA_ADAPTER = "mnemex.accounts.adapters.MnemexMFAAdapter"
MFA_ALLOW_UNVERIFIED_EMAIL = False
MFA_RECOVERY_CODES_SHOW_ONCE = True
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TOTP_ISSUER = "MNEMEX"
MFA_TOTP_PERIOD = 30
MFA_TOTP_TOLERANCE = 1
MFA_TRUST_ENABLED = False
MFA_FORMS = {
    "authenticate": "mnemex.accounts.forms.MnemexAuthenticateForm",
    "reauthenticate": "mnemex.accounts.forms.MnemexReauthenticateForm",
}

# Allauth uses Django's default cache for application rate limits. Security
# claims have a separate alias so their atomic one-time keys cannot collide
# with throttle or ordinary application state. Production replaces both
# local-memory backends with independently prefixed shared Redis aliases.
CACHES: dict[str, dict[str, Any]] = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "mnemex-rate-limits",
        "KEY_PREFIX": "mnemex:rate-limits",
    },
    "security": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "mnemex-security-claims",
        "KEY_PREFIX": "mnemex:security",
    },
}
MNEMEX_SECURITY_CACHE_ALIAS = "security"
ALLAUTH_TRUSTED_PROXY_COUNT = 0
ALLAUTH_TRUSTED_CLIENT_IP_HEADER = None

# Authenticator secrets are unusable without an explicitly configured,
# versioned application key. Tests provide a synthetic key; hosted settings
# must provide their own before privileged authorization can ever be enabled.
MNEMEX_MFA_ENCRYPTION_KEYS: dict[int, bytes] = {}
MNEMEX_MFA_ACTIVE_KEY_VERSION: int | None = None
MNEMEX_NOTIFICATION_ENCRYPTION_KEYS: dict[int, bytes] = {}
MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION: int | None = None
MNEMEX_PRIVILEGED_MFA_MAX_AGE_SECONDS = 8 * 60 * 60
MNEMEX_SENSITIVE_MFA_MAX_AGE_SECONDS = 5 * 60
MNEMEX_ACTION_TICKET_TTL_SECONDS = 90
MNEMEX_PRIVILEGED_ACTION_TICKETS_REQUIRED = False

# An explicit private local directory may be provided for development. Hosted
# object storage needs its own adapter and production authorization.
MNEMEX_PRIVATE_ARTIFACT_ROOT: str | Path | None = None
MNEMEX_PRIVATE_ARTIFACT_BUCKET_IS_PUBLIC = False

# Fail closed unless a non-production settings module explicitly enables the
# local pilot path. A timestamp recording MFA enrollment is not session-bound
# MFA assurance and must never authorize hosted privileged operations.
MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED = False
MNEMEX_HOSTED_CONFIGURATION = False

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
