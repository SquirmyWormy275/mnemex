from __future__ import annotations

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                (
                    "event_id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("actor_id", models.UUIDField(blank=True, null=True)),
                ("action", models.CharField(max_length=120)),
                ("target_type", models.CharField(max_length=80)),
                ("target_id", models.CharField(max_length=160)),
                ("correlation_id", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("payload_digest", models.CharField(max_length=64)),
                ("metadata", models.JSONField(default=dict)),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ("occurred_at", "event_id"),
                "default_permissions": ("add", "view"),
            },
        ),
        migrations.CreateModel(
            name="IdempotencyRecord",
            fields=[
                (
                    "record_id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("scope", models.CharField(max_length=120)),
                ("key", models.CharField(max_length=200)),
                ("request_digest", models.CharField(max_length=64)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("in_progress", "In progress"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="in_progress",
                        max_length=20,
                    ),
                ),
                ("response", models.JSONField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["target_type", "target_id"], name="audit_target_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["correlation_id"], name="audit_correlation_idx"),
        ),
        migrations.AddConstraint(
            model_name="idempotencyrecord",
            constraint=models.UniqueConstraint(
                fields=("scope", "key"), name="unique_idempotency_scope_key"
            ),
        ),
        migrations.AddIndex(
            model_name="idempotencyrecord",
            index=models.Index(fields=["scope", "status"], name="idempotency_status_idx"),
        ),
    ]
