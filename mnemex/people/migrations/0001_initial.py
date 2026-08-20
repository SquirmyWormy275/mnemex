from __future__ import annotations

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Person",
            fields=[
                (
                    "person_id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("merged", "Merged"),
                            ("redacted", "Redacted"),
                        ],
                        default="active",
                        max_length=20,
                    ),
                ),
                (
                    "age_classification",
                    models.CharField(
                        choices=[
                            ("unknown", "Unknown"),
                            ("minor", "Minor"),
                            ("adult", "Adult"),
                        ],
                        default="unknown",
                        max_length=20,
                    ),
                ),
                ("age_policy_version", models.CharField(blank=True, max_length=80)),
                ("age_transitioned_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("revision", models.PositiveIntegerField(default=1)),
                (
                    "account",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="competitor_person",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "merged_into",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="merged_people",
                        to="people.person",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="LegalIdentityClaim",
            fields=[
                (
                    "claim_id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("encrypted_payload", models.BinaryField()),
                ("lookup_token", models.CharField(db_index=True, max_length=64)),
                ("encryption_key_version", models.PositiveIntegerField()),
                ("source", models.CharField(max_length=120)),
                (
                    "verification_state",
                    models.CharField(
                        choices=[
                            ("unverified", "Unverified"),
                            ("self_asserted", "Self asserted"),
                            ("source_asserted", "Source asserted"),
                            ("verified", "Verified"),
                            ("expired", "Expired"),
                            ("revoked", "Revoked"),
                            ("disputed", "Disputed"),
                        ],
                        default="unverified",
                        max_length=24,
                    ),
                ),
                ("evidence_reference", models.CharField(blank=True, max_length=240)),
                ("policy_version", models.CharField(max_length=80)),
                ("retention_rule", models.CharField(max_length=160)),
                ("valid_from", models.DateTimeField(default=django.utils.timezone.now)),
                ("valid_until", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("disputed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("revision", models.PositiveIntegerField(default=1)),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="legal_identity_claims",
                        to="people.person",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="GuardianRelationship",
            fields=[
                (
                    "relationship_id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("authority_basis", models.CharField(max_length=120)),
                (
                    "verification_state",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("verified", "Verified"),
                            ("rejected", "Rejected"),
                            ("expired", "Expired"),
                            ("revoked", "Revoked"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("evidence_reference", models.CharField(blank=True, max_length=240)),
                ("jurisdiction", models.CharField(max_length=80)),
                ("policy_version", models.CharField(max_length=80)),
                ("effective_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                ("revocation_reason", models.CharField(blank=True, max_length=240)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("revision", models.PositiveIntegerField(default=1)),
                (
                    "guardian_account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="guardian_relationships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "minor_person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="guardian_relationships",
                        to="people.person",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Alias",
            fields=[
                (
                    "alias_id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("value", models.CharField(max_length=200)),
                ("normalized_value", models.CharField(max_length=200)),
                ("source", models.CharField(max_length=120)),
                (
                    "confidence",
                    models.DecimalField(blank=True, decimal_places=4, max_digits=5, null=True),
                ),
                (
                    "review_state",
                    models.CharField(
                        choices=[
                            ("unreviewed", "Unreviewed"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("disputed", "Disputed"),
                        ],
                        default="unreviewed",
                        max_length=20,
                    ),
                ),
                ("is_public", models.BooleanField(default=False)),
                ("valid_from", models.DateTimeField(blank=True, null=True)),
                ("valid_until", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("revision", models.PositiveIntegerField(default=1)),
                (
                    "person",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="aliases",
                        to="people.person",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="person",
            index=models.Index(fields=["status", "age_classification"], name="person_state_idx"),
        ),
        migrations.AddIndex(
            model_name="legalidentityclaim",
            index=models.Index(
                fields=["person", "verification_state"], name="legal_claim_state_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="guardianrelationship",
            index=models.Index(
                fields=["minor_person", "verification_state", "revoked_at"],
                name="guardian_authority_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="alias",
            constraint=models.UniqueConstraint(
                fields=("person", "normalized_value", "source"),
                name="unique_person_alias_source",
            ),
        ),
    ]
