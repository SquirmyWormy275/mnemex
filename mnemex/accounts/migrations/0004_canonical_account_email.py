from __future__ import annotations

from django.db import migrations, models
from django.db.models.functions import Lower


def canonicalize_account_emails(apps, schema_editor) -> None:
    Account = apps.get_model("accounts", "Account")
    EmailAddress = apps.get_model("account", "EmailAddress")
    collisions: dict[str, list[str]] = {}
    for account_id, email in Account.objects.order_by("account_id").values_list(
        "account_id", "email"
    ):
        canonical = email.strip().lower()
        collisions.setdefault(canonical, []).append(str(account_id))
    duplicates = {email: ids for email, ids in collisions.items() if len(ids) > 1}
    if duplicates:
        raise RuntimeError(
            f"{len(duplicates)} case-insensitive account email collision group(s) "
            "must be resolved before migration"
        )

    address_collisions: dict[tuple[str, str], list[int]] = {}
    verified_address_users: dict[str, set[str]] = {}
    addresses = list(
        EmailAddress.objects.order_by("id").values_list("id", "user_id", "email", "verified")
    )
    for address_id, user_id, email, verified in addresses:
        key = (str(user_id), email.strip().lower())
        address_collisions.setdefault(key, []).append(address_id)
        if verified:
            verified_address_users.setdefault(key[1], set()).add(str(user_id))
    duplicate_addresses = [ids for ids in address_collisions.values() if len(ids) > 1]
    if duplicate_addresses:
        raise RuntimeError(
            f"{len(duplicate_addresses)} case-insensitive related email collision group(s) "
            "must be resolved before migration"
        )
    verified_collisions = [
        user_ids for user_ids in verified_address_users.values() if len(user_ids) > 1
    ]
    if verified_collisions:
        raise RuntimeError(
            f"{len(verified_collisions)} case-insensitive verified related email collision "
            "group(s) must be resolved before migration"
        )

    for canonical, account_ids in collisions.items():
        Account.objects.filter(account_id=account_ids[0]).update(email=canonical)
    for (_user_id, canonical), address_ids in address_collisions.items():
        EmailAddress.objects.filter(id=address_ids[0]).update(email=canonical)


class Migration(migrations.Migration):
    dependencies = [
        ("account", "0009_emailaddress_unique_primary_email"),
        ("accounts", "0003_privileged_role_tenant_scope"),
    ]

    operations = [
        migrations.RunPython(canonicalize_account_emails, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="account",
            constraint=models.UniqueConstraint(
                Lower("email"),
                name="unique_account_email_ci",
            ),
        ),
    ]
