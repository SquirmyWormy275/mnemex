from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mnemex.accounts"
    label = "accounts"

    def ready(self) -> None:
        from mnemex.accounts import signals  # noqa: F401
        from mnemex.web import checks  # noqa: F401
