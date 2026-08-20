from __future__ import annotations

from django.apps import AppConfig


class CareerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mnemex.career"
    verbose_name = "MNEMEX career history"
