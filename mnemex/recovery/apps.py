from __future__ import annotations

from django.apps import AppConfig


class RecoveryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mnemex.recovery"
    label = "recovery"
    verbose_name = "MNEMEX Recovery Evidence"
