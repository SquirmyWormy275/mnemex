from __future__ import annotations

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="RecoveryManifest",
            fields=[
                (
                    "manifest_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("database_snapshot_identity", models.CharField(max_length=160)),
                ("object_inventory_digest", models.CharField(max_length=64)),
                ("object_count", models.PositiveBigIntegerField()),
                ("required_mfa_key_versions", models.JSONField(default=list)),
                ("required_notification_key_versions", models.JSONField(default=list)),
                ("application_schema_version", models.CharField(max_length=160)),
                ("environment_fingerprint", models.CharField(max_length=64)),
                ("payload_digest", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "default_permissions": ("add", "view"),
                "ordering": ("-created_at", "manifest_id"),
            },
        ),
        migrations.CreateModel(
            name="RecoveryRehearsalRecord",
            fields=[
                (
                    "record_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "result",
                    models.CharField(
                        choices=[("pass", "Pass"), ("fail", "Fail")],
                        max_length=8,
                    ),
                ),
                ("environment_fingerprint", models.CharField(max_length=64)),
                ("issue_codes", models.JSONField(blank=True, default=list)),
                ("normalized_lease_count", models.PositiveIntegerField(default=0)),
                ("evidence_digest", models.CharField(max_length=64)),
                ("observed_at", models.DateTimeField()),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "manifest",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="rehearsal_records",
                        to="recovery.recoverymanifest",
                    ),
                ),
            ],
            options={
                "default_permissions": ("add", "view"),
                "ordering": ("-observed_at", "record_id"),
            },
        ),
        migrations.AddIndex(
            model_name="recoverymanifest",
            index=models.Index(
                fields=["environment_fingerprint", "-created_at"],
                name="recovery_manifest_env_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="recoveryrehearsalrecord",
            constraint=models.UniqueConstraint(
                fields=("manifest", "observed_at", "evidence_digest"),
                name="unique_recovery_rehearsal_fact",
            ),
        ),
        migrations.AddIndex(
            model_name="recoveryrehearsalrecord",
            index=models.Index(
                fields=["environment_fingerprint", "-observed_at"],
                name="recovery_record_env_idx",
            ),
        ),
    ]
