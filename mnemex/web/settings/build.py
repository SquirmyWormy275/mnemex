"""Non-serving settings used only to collect static assets into an image."""

from mnemex.web.settings.base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "mnemex-build-only-not-a-runtime-secret"
ALLOWED_HOSTS = []
STATIC_ROOT = BASE_DIR / "staticfiles"  # noqa: F405
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED = False
