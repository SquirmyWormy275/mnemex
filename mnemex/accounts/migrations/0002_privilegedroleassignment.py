from __future__ import annotations

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="PrivilegedRoleAssignment",
            fields=[
                (
                    "assignment_id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("results_manager", "Results manager"),
                            ("export_reviewer", "Results export reviewer"),
                            ("identity_reviewer", "Identity reviewer"),
                            ("privacy_officer", "Privacy officer"),
                            ("partner_administrator", "Partner administrator"),
                        ],
                        max_length=40,
                    ),
                ),
                ("assigned_at", models.DateTimeField(auto_now_add=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("revocation_reason", models.CharField(blank=True, max_length=240)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="privileged_roles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "assigned_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="assigned_privileged_roles",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [models.Index(fields=["role", "revoked_at"], name="role_active_idx")],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("revoked_at__isnull", True)),
                        fields=("account", "role"),
                        name="unique_active_privileged_role",
                    )
                ],
            },
        )
    ]
