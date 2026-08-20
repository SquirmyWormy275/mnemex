from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager

if TYPE_CHECKING:
    from mnemex.accounts.models import Account  # noqa: F401


class AccountManager(BaseUserManager["Account"]):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields: Any) -> "Account":
        if not email:
            raise ValueError("An email address is required")
        normalized_email = self.normalize_email(email).strip().lower()
        account = self.model(email=normalized_email, **extra_fields)
        account.set_password(password)
        account.save(using=self._db)
        return account

    def create_user(
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> "Account":
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self, email: str, password: str | None = None, **extra_fields: Any
    ) -> "Account":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True")
        return self._create_user(email, password, **extra_fields)
