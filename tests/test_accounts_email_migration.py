from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_account_email_migration_rejects_cross_user_verified_case_collision_without_pii() -> None:
    old_target = ("accounts", "0003_privileged_role_tenant_scope")
    email_target = ("account", "0009_emailaddress_unique_primary_email")
    new_target = ("accounts", "0004_canonical_account_email")
    executor = MigrationExecutor(connection)
    leaf_targets = executor.loader.graph.leaf_nodes()
    EmailAddress = None

    try:
        executor.migrate([old_target, email_target])
        old_apps = executor.loader.project_state([old_target, email_target]).apps
        Account = old_apps.get_model("accounts", "Account")
        EmailAddress = old_apps.get_model("account", "EmailAddress")
        first = Account.objects.create(email="first@example.invalid", password="!")
        second = Account.objects.create(email="second@example.invalid", password="!")
        EmailAddress.objects.create(
            user=first,
            email="Private.Alternate@example.invalid",
            verified=True,
            primary=False,
        )
        EmailAddress.objects.create(
            user=second,
            email="private.alternate@example.invalid",
            verified=True,
            primary=False,
        )

        executor = MigrationExecutor(connection)
        with pytest.raises(RuntimeError) as exc_info:
            executor.migrate([new_target])

        message = str(exc_info.value)
        assert "verified related email collision group" in message
        assert "Private.Alternate" not in message
        assert "private.alternate" not in message
    finally:
        if EmailAddress is not None:
            EmailAddress.objects.all().delete()
        MigrationExecutor(connection).migrate(leaf_targets)
