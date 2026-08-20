from __future__ import annotations

import hashlib

import django.core.validators
import django.utils.timezone
from django.db import migrations, models


def normalize_existing_jobs(apps, schema_editor):
    job_model = apps.get_model("legacy_migration", "LegacyMigrationJob")
    seen_active_apply_requests: set[tuple[object, str, int]] = set()
    for job in job_model.objects.select_related("run").order_by("created_at", "job_id"):
        digest = ""
        if job.job_kind == "apply":
            candidate = job.run.dry_run_manifest_digest
            if not isinstance(candidate, str) or len(candidate) != 64:
                candidate = hashlib.sha256(f"legacy-unclaimable:{job.pk}".encode()).hexdigest()
                job.status = "failed"
                job.last_error_code = "legacy_job_not_claimable"
                job.last_error_message = "legacy job requires operator review"
            digest = candidate
            job.request_rationale = "Imported legacy APPLY request; operator review required."
        job.requested_manifest_digest = digest
        job.max_attempts = max(5, job.attempt_count)
        job.failure_count = job.attempt_count
        if job.status in {"running", "interrupted"}:
            if job.failure_count >= job.max_attempts:
                job.status = "failed"
                job.completed_at = django.utils.timezone.now()
                job.last_error_code = "attempts_exhausted"
                job.last_error_message = "worker attempts exhausted; operator review is required"
            else:
                job.status = "retry_wait"
        if job.job_kind == "apply" and job.status in {"pending", "running", "retry_wait"}:
            request_key = (job.run_id, digest, 250)
            if request_key in seen_active_apply_requests:
                job.status = "failed"
                job.completed_at = django.utils.timezone.now()
                job.last_error_code = "legacy_duplicate_job"
                job.last_error_message = "legacy job requires operator review"
            else:
                seen_active_apply_requests.add(request_key)
        job.claim_generation = job.attempt_count
        job.claim_token = ""
        job.claim_owner = ""
        job.heartbeat_at = None
        job.lease_expires_at = None
        job.save(
            update_fields=[
                "status",
                "requested_manifest_digest",
                "request_rationale",
                "max_attempts",
                "failure_count",
                "claim_generation",
                "claim_token",
                "claim_owner",
                "heartbeat_at",
                "lease_expires_at",
                "last_error_code",
                "last_error_message",
                "completed_at",
            ]
        )


def restore_legacy_job_statuses(apps, schema_editor):
    job_model = apps.get_model("legacy_migration", "LegacyMigrationJob")
    job_model.objects.filter(status__in=("retry_wait", "cancelled")).update(status="interrupted")


class Migration(migrations.Migration):
    dependencies = [("legacy_migration", "0003_allow_empty_header_candidates")]

    operations = [
        migrations.AddField(
            model_name="legacymigrationjob",
            name="available_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name="legacymigrationjob",
            name="chunk_size",
            field=models.PositiveIntegerField(default=250),
        ),
        migrations.AddField(
            model_name="legacymigrationjob",
            name="failure_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="legacymigrationjob",
            name="claim_generation",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="legacymigrationjob",
            name="claim_owner",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="legacymigrationjob",
            name="claim_token",
            field=models.CharField(
                blank=True,
                max_length=64,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Enter an opaque 64-character claim token.",
                        regex="^[0-9a-f]{64}$",
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="legacymigrationjob",
            name="heartbeat_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="legacymigrationjob",
            name="lease_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="legacymigrationjob",
            name="max_attempts",
            field=models.PositiveIntegerField(
                default=5, validators=[django.core.validators.MinValueValidator(1)]
            ),
        ),
        migrations.AddField(
            model_name="legacymigrationjob",
            name="requested_manifest_digest",
            field=models.CharField(
                blank=True,
                max_length=64,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Enter a lowercase SHA-256 digest.",
                        regex="^[0-9a-f]{64}$",
                    )
                ],
            ),
        ),
        migrations.AddField(
            model_name="legacymigrationjob",
            name="request_rationale",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AlterField(
            model_name="legacymigrationjob",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("running", "Running"),
                    ("retry_wait", "Retry wait"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.RunPython(normalize_existing_jobs, restore_legacy_job_statuses),
        migrations.AddConstraint(
            model_name="legacymigrationjob",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    job_kind="apply", status__in=("pending", "running", "retry_wait")
                ),
                fields=("run", "job_kind", "requested_manifest_digest", "chunk_size"),
                name="uniq_active_legacy_job_req",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacymigrationjob",
            constraint=models.CheckConstraint(
                condition=models.Q(chunk_size__gte=1, chunk_size__lte=250),
                name="legacy_job_chunk_bounds",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacymigrationjob",
            constraint=models.CheckConstraint(
                condition=models.Q(max_attempts__gte=1),
                name="legacy_job_max_attempts",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacymigrationjob",
            constraint=models.CheckConstraint(
                condition=models.Q(failure_count__lte=models.F("max_attempts")),
                name="legacy_job_failures_lte_max",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacymigrationjob",
            constraint=models.CheckConstraint(
                condition=models.Q(attempt_count=models.F("claim_generation")),
                name="legacy_job_claim_counter_sync",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacymigrationjob",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        status="running",
                        claim_owner__gt="",
                        claim_token__gt="",
                        heartbeat_at__isnull=False,
                        lease_expires_at__isnull=False,
                    )
                    | (
                        ~models.Q(status="running")
                        & models.Q(
                            claim_owner="",
                            claim_token="",
                            heartbeat_at__isnull=True,
                            lease_expires_at__isnull=True,
                        )
                    )
                ),
                name="legacy_job_claim_shape",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacymigrationjob",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(job_kind="apply", requested_manifest_digest__gt="")
                    | ~models.Q(job_kind="apply")
                ),
                name="legacy_apply_manifest_shape",
            ),
        ),
        migrations.AddConstraint(
            model_name="legacymigrationjob",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(job_kind="apply", request_rationale__gt="")
                    | ~models.Q(job_kind="apply")
                ),
                name="legacy_apply_rationale_shape",
            ),
        ),
        migrations.AddIndex(
            model_name="legacymigrationjob",
            index=models.Index(
                fields=["job_kind", "status", "available_at", "created_at"],
                name="legacy_job_claim_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="legacymigrationjob",
            index=models.Index(
                fields=["job_kind", "status", "lease_expires_at"],
                name="legacy_job_lease_idx",
            ),
        ),
    ]
