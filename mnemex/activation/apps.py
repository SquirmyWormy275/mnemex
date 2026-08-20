from django.apps import AppConfig


class ActivationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mnemex.activation"
    label = "activation"

    def ready(self) -> None:
        from . import checks  # noqa: F401
