from __future__ import annotations

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_security_notification_outbox"),
    ]

    operations = [
        migrations.CreateModel(
            name="EncryptionKeyRotationJob",
            fields=[
                (
                    "rotation_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "purpose",
                    models.CharField(
                        choices=[("mfa", "MFA authenticator")],
                        default="mfa",
                        max_length=24,
                    ),
                ),
                ("source_key_version", models.PositiveIntegerField()),
                ("target_key_version", models.PositiveIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("retry_wait", "Retry wait"),
                            ("completed", "Completed"),
                            ("failed_review", "Failed - review required"),
                        ],
                        default="pending",
                        max_length=24,
                    ),
                ),
                ("available_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("cursor_authenticator_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("scanned_count", models.PositiveBigIntegerField(default=0)),
                ("processed_count", models.PositiveBigIntegerField(default=0)),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("failure_count", models.PositiveIntegerField(default=0)),
                ("max_attempts", models.PositiveSmallIntegerField(default=5)),
                ("claim_token", models.CharField(blank=True, max_length=64)),
                ("claim_owner", models.CharField(blank=True, max_length=120)),
                ("claim_generation", models.PositiveIntegerField(default=0)),
                ("heartbeat_at", models.DateTimeField(blank=True, null=True)),
                ("lease_expires_at", models.DateTimeField(blank=True, null=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("last_error_code", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "requested_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="requested_key_rotations",
                        to="accounts.account",
                    ),
                ),
            ],
            options={
                "ordering": ("created_at", "rotation_id"),
                "default_permissions": ("add", "change", "view"),
                "indexes": [
                    models.Index(
                        fields=["status", "available_at"],
                        name="key_rotation_ready_idx",
                    ),
                    models.Index(
                        fields=["status", "lease_expires_at"],
                        name="key_rotation_lease_idx",
                    ),
                    models.Index(
                        fields=["purpose", "source_key_version", "status"],
                        name="key_rotation_source_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            ("source_key_version", models.F("target_key_version")),
                            _negated=True,
                        ),
                        name="key_rotation_versions_differ",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(processed_count__lte=models.F("scanned_count")),
                        name="key_rotation_processed_lte_scanned",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(max_attempts__gte=1, max_attempts__lte=10),
                        name="key_rotation_attempt_limit",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(failure_count__lte=models.F("attempt_count")),
                        name="key_rotation_failures_lte_attempts",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("status", "running"), _negated=True),
                            models.Q(
                                models.Q(("claim_token", ""), _negated=True),
                                models.Q(("claim_owner", ""), _negated=True),
                                ("lease_expires_at__isnull", False),
                            ),
                            _connector="OR",
                        ),
                        name="key_rotation_running_claimed",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(status__in=("pending", "running", "retry_wait")),
                        fields=("purpose", "source_key_version", "target_key_version"),
                        name="unique_active_key_rotation",
                    ),
                ],
            },
        ),
    ]
