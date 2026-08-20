from __future__ import annotations

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("partners", "0001_initial"),
        ("people", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ConsentGrant",
            fields=[
                (
                    "grant_id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("purpose", models.CharField(max_length=120)),
                ("field_groups", models.JSONField(default=list)),
                ("context_id", models.CharField(max_length=160)),
                (
                    "verification_threshold",
                    models.CharField(default="self_asserted", max_length=40),
                ),
                ("issued_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("revocation_reason", models.CharField(blank=True, max_length=240)),
                ("policy_version", models.CharField(max_length=80)),
                ("revision", models.PositiveIntegerField(default=1)),
                (
                    "acting_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="issued_consent_grants",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "guardian_relationship",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="consent_grants",
                        to="people.guardianrelationship",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="consent_grants",
                        to="people.person",
                    ),
                ),
                (
                    "recipient_client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="consent_grants",
                        to="partners.partnerclient",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["person", "recipient_client", "purpose", "revoked_at"],
                        name="consent_disclosure_idx",
                    )
                ]
            },
        ),
        migrations.CreateModel(
            name="PublicProfileOptIn",
            fields=[
                (
                    "opt_in_id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("selected_fields", models.JSONField(default=list)),
                ("policy_version", models.CharField(max_length=80)),
                ("effective_at", models.DateTimeField(auto_now_add=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("revocation_reason", models.CharField(blank=True, max_length=240)),
                ("revision", models.PositiveIntegerField(default=1)),
                (
                    "acting_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="public_profile_opt_ins",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "guardian_relationship",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="public_profile_opt_ins",
                        to="people.guardianrelationship",
                    ),
                ),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="public_profile_opt_ins",
                        to="people.person",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["person", "revoked_at"], name="public_opt_in_active_idx")
                ]
            },
        ),
    ]
