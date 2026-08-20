from __future__ import annotations

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ActivationEvidence",
            fields=[
                (
                    "evidence_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("gate_id", models.CharField(max_length=48)),
                (
                    "result",
                    models.CharField(
                        choices=[("pending", "Pending"), ("pass", "Pass"), ("fail", "Fail")],
                        max_length=12,
                    ),
                ),
                ("source", models.CharField(max_length=48)),
                ("environment_fingerprint", models.CharField(max_length=64)),
                ("evidence_time", models.DateTimeField()),
                ("expires_at", models.DateTimeField()),
                ("summary_code", models.CharField(max_length=120)),
                ("payload_digest", models.CharField(max_length=64)),
                ("recorded_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "default_permissions": ("add", "view"),
                "ordering": ("gate_id", "-evidence_time", "-recorded_at", "evidence_id"),
            },
        ),
        migrations.AddConstraint(
            model_name="activationevidence",
            constraint=models.UniqueConstraint(
                fields=(
                    "gate_id",
                    "environment_fingerprint",
                    "evidence_time",
                    "payload_digest",
                ),
                name="unique_activation_evidence_fact",
            ),
        ),
        migrations.AddIndex(
            model_name="activationevidence",
            index=models.Index(
                fields=["environment_fingerprint", "gate_id", "-evidence_time"],
                name="activation_current_idx",
            ),
        ),
    ]
