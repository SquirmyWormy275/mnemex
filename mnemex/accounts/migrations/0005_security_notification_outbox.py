from __future__ import annotations

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_canonical_account_email"),
    ]

    operations = [
        migrations.CreateModel(
            name="SecurityNotification",
            fields=[
                (
                    "notification_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("template_identifier", models.CharField(max_length=160)),
                ("context_code", models.CharField(max_length=80)),
                ("idempotency_key", models.CharField(max_length=64, unique=True)),
                ("message_id", models.CharField(max_length=160, unique=True)),
                ("recipient_ciphertext", models.TextField()),
                ("recipient_hmac", models.CharField(max_length=64)),
                ("encryption_key_version", models.PositiveIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("retry_wait", "Retry wait"),
                            ("delivered", "Delivered"),
                            ("failed_review", "Failed - review required"),
                            ("delivery_uncertain", "Delivery uncertain"),
                            ("expired", "Recipient retention expired"),
                        ],
                        default="pending",
                        max_length=24,
                    ),
                ),
                (
                    "delivery_phase",
                    models.CharField(
                        choices=[
                            ("pre_handoff", "Before SMTP handoff"),
                            ("handoff", "SMTP handoff began"),
                        ],
                        default="pre_handoff",
                        max_length=20,
                    ),
                ),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("failure_count", models.PositiveIntegerField(default=0)),
                ("max_attempts", models.PositiveSmallIntegerField(default=5)),
                ("available_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("claim_token", models.CharField(blank=True, max_length=64)),
                ("claim_owner", models.CharField(blank=True, max_length=120)),
                ("claim_generation", models.PositiveIntegerField(default=0)),
                ("heartbeat_at", models.DateTimeField(blank=True, null=True)),
                ("lease_expires_at", models.DateTimeField(blank=True, null=True)),
                ("handoff_at", models.DateTimeField(blank=True, null=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("review_required_at", models.DateTimeField(blank=True, null=True)),
                ("recipient_retention_deadline", models.DateTimeField()),
                ("recipient_purged_at", models.DateTimeField(blank=True, null=True)),
                ("last_error_code", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="security_notifications",
                        to="accounts.account",
                    ),
                ),
            ],
            options={
                "ordering": ("created_at", "notification_id"),
                "default_permissions": ("add", "change", "view"),
                "indexes": [
                    models.Index(fields=["status", "available_at"], name="notify_ready_idx"),
                    models.Index(fields=["status", "lease_expires_at"], name="notify_lease_idx"),
                    models.Index(
                        fields=["recipient_purged_at", "recipient_retention_deadline"],
                        name="notify_retention_idx",
                    ),
                    models.Index(fields=["account", "created_at"], name="notify_account_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("max_attempts__gte", 1), ("max_attempts__lte", 10)),
                        name="notify_attempt_limit_valid",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("failure_count__lte", models.F("attempt_count"))),
                        name="notify_failures_lte_attempts",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("recipient_purged_at__isnull", True),
                            ("recipient_ciphertext", ""),
                            _connector="OR",
                        ),
                        name="notify_purged_cipher_empty",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("status", "running"),
                            _negated=True,
                        )
                        | (
                            ~models.Q(("claim_token", ""))
                            & ~models.Q(("claim_owner", ""))
                            & models.Q(("lease_expires_at__isnull", False))
                        ),
                        name="notify_running_has_claim",
                    ),
                ],
            },
        ),
    ]
