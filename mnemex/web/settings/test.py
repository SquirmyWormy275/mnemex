from __future__ import annotations

import os

from mnemex.web.database import assert_safe_test_database, database_config_from_url
from mnemex.web.settings.base import *  # noqa: F403

SECRET_KEY = "mnemex-test-only-secret-key-never-use-outside-tests"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
# Tests explicitly enable the isolated synthetic pilot path. Production remains
# fail-closed until hosted account-security prerequisites are configured.
MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED = True
MNEMEX_MFA_ENCRYPTION_KEYS = {1: b"m" * 32}
MNEMEX_MFA_ACTIVE_KEY_VERSION = 1
MNEMEX_NOTIFICATION_ENCRYPTION_KEYS = {1: b"n" * 32}
MNEMEX_NOTIFICATION_ACTIVE_KEY_VERSION = 1
_test_database_url = os.environ.get("MNEMEX_TEST_DATABASE_URL")
if _test_database_url:
    DATABASES = {"default": database_config_from_url(_test_database_url)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
assert_safe_test_database(DATABASES["default"])

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
