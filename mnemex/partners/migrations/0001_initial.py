from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.CreateModel(
            name="PartnerOrganization",
            fields=[
                (
                    "organization_id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("name", models.CharField(max_length=160, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("suspended", "Suspended")],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("revision", models.PositiveIntegerField(default=1)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="PartnerClient",
            fields=[
                (
                    "client_id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("name", models.CharField(max_length=160)),
                (
                    "environment",
                    models.CharField(
                        choices=[
                            ("sandbox", "Sandbox"),
                            ("staging", "Staging"),
                            ("production", "Production"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("suspended", "Suspended"),
                            ("revoked", "Revoked"),
                        ],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("allowed_purposes", models.JSONField(default=list)),
                ("allowed_field_groups", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("revision", models.PositiveIntegerField(default=1)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="clients",
                        to="partners.partnerorganization",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["organization", "environment", "status"],
                        name="partner_client_scope_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "name", "environment"),
                        name="unique_partner_client_environment",
                    )
                ],
            },
        ),
    ]
