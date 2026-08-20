from __future__ import annotations

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_durable_job_migration_normalizes_exhaustion_and_reverses_statuses() -> None:
    old_target = ("legacy_migration", "0003_allow_empty_header_candidates")
    new_target = ("legacy_migration", "0004_durable_apply_job_leases")
    executor = MigrationExecutor(connection)
    leaf_targets = executor.loader.graph.leaf_nodes()

    try:
        executor.migrate([old_target])
        old_apps = executor.loader.project_state([old_target]).apps
        Account = old_apps.get_model("accounts", "Account")
        PartnerOrganization = old_apps.get_model("partners", "PartnerOrganization")
        SourceArtifact = old_apps.get_model("results", "SourceArtifact")
        LegacySourceInventory = old_apps.get_model("legacy_migration", "LegacySourceInventory")
        LegacyMigrationRun = old_apps.get_model("legacy_migration", "LegacyMigrationRun")
        LegacyMigrationJob = old_apps.get_model("legacy_migration", "LegacyMigrationJob")

        account = Account.objects.create(
            email="migration-worker-test@mnemex.example.invalid",
            password="!",
        )
        organization = PartnerOrganization.objects.create(name="Migration worker test tenant")
        job_ids: list[object] = []
        cases = ((0, "running"), (4, "interrupted"), (5, "running"), (6, "running"))
        for sequence, (attempt_count, status) in enumerate(cases, start=1):
            digest = f"{sequence:064x}"
            artifact = SourceArtifact.objects.create(
                organization=organization,
                kind="spreadsheet",
                digest=digest,
                original_name=f"migration-{sequence}.xlsx",
                content_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                byte_size=1,
                object_reference=f"private/{digest}.xlsx",
                uploaded_by=account,
            )
            inventory = LegacySourceInventory.objects.create(
                organization=organization,
                artifact=artifact,
                source_namespace="migration-test",
                source_key=f"migration-{sequence}",
                data_rights_reference="synthetic-test-authorization",
                parser_version="migration-test-v1",
                manifest_digest=digest,
                created_by=account,
            )
            run = LegacyMigrationRun.objects.create(
                organization=organization,
                inventory=inventory,
                run_version=1,
                ruleset_version="migration-test-v1",
                state="approved",
                dry_run_manifest_digest=digest,
                created_by=account,
            )
            job = LegacyMigrationJob.objects.create(
                organization=organization,
                run=run,
                job_kind="apply",
                job_sequence=1,
                status=status,
                attempt_count=attempt_count,
                created_by=account,
            )
            job_ids.append(job.pk)

        history_run = run
        history_jobs: dict[str, object] = {}
        for sequence, status in (
            (2, "failed"),
            (3, "completed"),
            (4, "pending"),
            (5, "interrupted"),
        ):
            job = LegacyMigrationJob.objects.create(
                organization=organization,
                run=history_run,
                job_kind="apply",
                job_sequence=sequence,
                status=status,
                attempt_count=0,
                created_by=account,
            )
            history_jobs[status] = job.pk

        executor = MigrationExecutor(connection)
        executor.migrate([new_target])
        new_apps = executor.loader.project_state([new_target]).apps
        NewJob = new_apps.get_model("legacy_migration", "LegacyMigrationJob")
        jobs = [NewJob.objects.get(pk=job_id) for job_id in job_ids]

        assert [job.failure_count for job in jobs] == [0, 4, 5, 6]
        assert [job.max_attempts for job in jobs] == [5, 5, 5, 6]
        assert [job.status for job in jobs] == [
            "retry_wait",
            "retry_wait",
            "failed",
            "failed",
        ]
        assert jobs[2].last_error_code == jobs[3].last_error_code == "attempts_exhausted"
        assert all(job.request_rationale for job in jobs)
        migrated_history = {
            status: NewJob.objects.get(pk=job_id) for status, job_id in history_jobs.items()
        }
        assert migrated_history["failed"].status == "failed"
        assert migrated_history["completed"].status == "completed"
        assert migrated_history["failed"].requested_manifest_digest == run.dry_run_manifest_digest
        assert (
            migrated_history["completed"].requested_manifest_digest == run.dry_run_manifest_digest
        )
        active_history = [
            migrated_history["pending"].status,
            migrated_history["interrupted"].status,
        ]
        assert active_history.count("pending") + active_history.count("retry_wait") == 1
        assert active_history.count("failed") == 1

        cancelled = NewJob.objects.create(
            organization_id=jobs[0].organization_id,
            run_id=jobs[0].run_id,
            job_kind="apply",
            job_sequence=2,
            requested_manifest_digest="f" * 64,
            request_rationale="Synthetic cancelled request for reverse migration.",
            chunk_size=250,
            status="cancelled",
            created_by_id=jobs[0].created_by_id,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([old_target])
        reversed_apps = executor.loader.project_state([old_target]).apps
        ReversedJob = reversed_apps.get_model("legacy_migration", "LegacyMigrationJob")
        assert ReversedJob.objects.get(pk=job_ids[0]).status == "interrupted"
        assert ReversedJob.objects.get(pk=job_ids[1]).status == "interrupted"
        assert ReversedJob.objects.get(pk=cancelled.pk).status == "interrupted"
        assert ReversedJob.objects.get(pk=job_ids[2]).status == "failed"
    finally:
        MigrationExecutor(connection).migrate(leaf_targets)
