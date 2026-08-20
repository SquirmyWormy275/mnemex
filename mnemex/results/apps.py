from __future__ import annotations

from django.apps import AppConfig


class ResultsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mnemex.results"
    verbose_name = "MNEMEX Results Desk"
