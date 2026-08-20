from __future__ import annotations

from datetime import datetime
from datetime import timezone as datetime_timezone
from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from mnemex.accounts.models import Account
from mnemex.legacy_migration.models import (
    LegacyMigrationCheckpoint,
    LegacyMigrationDecisionRevision,
    LegacyMigrationJob,
    LegacyMigrationManifest,
    LegacyMigrationRowPreview,
    LegacyMigrationRun,
    LegacySourceInventory,
    LegacyTablePlan,
    LegacyWorksheetPlan,
)
from mnemex.partners.models import PartnerOrganization
from mnemex.results.models import PublishedSourceResult, SourceArtifact

pytestmark = pytest.mark.django_db


def _account(email: str) -> Account:
    return Account.objects.create_user(email=email, password="synthetic-password-123")


def _artifact(
    organization: PartnerOrganization,
    actor: Account,
    *,
    digest: str = "a" * 64,
) -> SourceArtifact:
    return SourceArtifact.objects.create(
        organization=organization,
        kind=SourceArtifact.Kind.SPREADSHEET,
        digest=digest,
        original_name="synthetic-legacy-results.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        byte_size=12_345,
        object_reference="synthetic/private/artifact.xlsx",
        uploaded_by=actor,
    )


def _inventory_and_run(
    organization: PartnerOrganization,
    actor: Account,
    *,
    digest: str = "a" * 64,
    run_version: int = 1,
) -> tuple[LegacySourceInventory, LegacyMigrationRun]:
    inventory = LegacySourceInventory.objects.create(
        organization=organization,
        artifact=_artifact(organization, actor, digest=digest),
        source_key=f"synthetic-source-{run_version}",
        data_rights_reference="synthetic-test-authorization",
        parser_version="xlsx-inspector-v1",
        manifest_digest="b" * 64,
        created_by=actor,
    )
    run = LegacyMigrationRun.objects.create(
        organization=organization,
        inventory=inventory,
        run_version=run_version,
        ruleset_version="legacy-rules-v1",
        created_by=actor,
    )
    return inventory, run


def _worksheet(
    run: LegacyMigrationRun,
    *,
    index: int = 0,
    name: str = "Synthetic Qualifiers",
    disposition: str = LegacyWorksheetPlan.Disposition.INCLUDED,
) -> LegacyWorksheetPlan:
    return LegacyWorksheetPlan.objects.create(
        organization=run.organization,
        run=run,
        sheet_index=index,
        sheet_name=name,
        visibility=LegacyWorksheetPlan.Visibility.VISIBLE,
        max_row=100,
        max_column=20,
        disposition=disposition,
        ignore_reason="synthetic summary sheet" if disposition == "ignored" else "",
        metadata_digest=("c" if index == 0 else "d") * 64,
        header_candidates=[5, 6],
    )


def _table(
    worksheet: LegacyWorksheetPlan,
    actor: Account,
    *,
    label: str = "qualifying",
    start_column: int = 1,
    end_column: int = 8,
) -> LegacyTablePlan:
    return LegacyTablePlan.objects.create(
        organization=worksheet.organization,
        run=worksheet.run,
        worksheet=worksheet,
        label=label,
        header_row=5,
        start_row=5,
        end_row=50,
        start_column=start_column,
        end_column=end_column,
        mapping_rules={
            "competitor_name": {"kind": "column", "column": "Competitor"},
            "source_result_id": {"kind": "derived", "name": "artifact_coordinate_id"},
        },
        mapping_digest=("e" if label == "qualifying" else "f") * 64,
        created_by=actor,
    )


def _preview(table: LegacyTablePlan, *, source_row: int = 6) -> LegacyMigrationRowPreview:
    if table.run.state == LegacyMigrationRun.State.DISCOVERED:
        table.run.state = LegacyMigrationRun.State.CONFIGURED
        table.run.save(update_fields=["state", "updated_at"])
    return LegacyMigrationRowPreview.objects.create(
        organization=table.organization,
        run=table.run,
        table_plan=table,
        source_sheet_index=table.worksheet.sheet_index,
        source_row_number=source_row,
        source_column_start=table.start_column,
        source_column_end=table.end_column,
        canonical_payload={"source_result_id": f"synthetic-{source_row}"},
        payload_digest="1" * 64,
        classification=LegacyMigrationRowPreview.Classification.PUBLISHABLE,
        validation_errors=[],
        source_state_digest="2" * 64,
    )


def test_domain_inventories_sheets_and_multiple_tables_without_publishing() -> None:
    actor = _account("inventory@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Inventory Show")
    inventory, run = _inventory_and_run(organization, actor)
    included = _worksheet(run)
    ignored = _worksheet(
        run,
        index=1,
        name="Synthetic Summary",
        disposition=LegacyWorksheetPlan.Disposition.IGNORED,
    )
    qualifier = _table(included, actor)
    final = _table(included, actor, label="final", start_column=10, end_column=17)

    assert inventory.artifact.organization_id == organization.pk
    assert list(run.worksheets.values_list("sheet_name", flat=True)) == [
        "Synthetic Qualifiers",
        "Synthetic Summary",
    ]
    assert ignored.table_plans.count() == 0
    assert set(included.table_plans.values_list("pk", flat=True)) == {
        qualifier.pk,
        final.pk,
    }
    assert PublishedSourceResult.objects.count() == 0


def test_cross_tenant_relationships_fail_closed() -> None:
    actor = _account("tenant-boundaries@mnemex.example.invalid")
    organization_a = PartnerOrganization.objects.create(name="Synthetic Tenant A")
    organization_b = PartnerOrganization.objects.create(name="Synthetic Tenant B")
    artifact_a = _artifact(organization_a, actor)

    with pytest.raises(ValidationError, match="artifact.*organization"):
        LegacySourceInventory.objects.create(
            organization=organization_b,
            artifact=artifact_a,
            source_key="synthetic-cross-tenant",
            data_rights_reference="synthetic-test-authorization",
            parser_version="xlsx-inspector-v1",
            manifest_digest="b" * 64,
            created_by=actor,
        )

    _, run_a = _inventory_and_run(organization_a, actor, digest="3" * 64)
    _, run_b = _inventory_and_run(organization_b, actor, digest="4" * 64)
    sheet_a = _worksheet(run_a)
    sheet_b = _worksheet(run_b)

    with pytest.raises(ValidationError, match="worksheet.*run"):
        LegacyTablePlan.objects.create(
            organization=organization_a,
            run=run_a,
            worksheet=sheet_b,
            label="cross-tenant",
            header_row=5,
            start_row=5,
            end_row=10,
            start_column=1,
            end_column=8,
            mapping_rules={},
            mapping_digest="5" * 64,
            created_by=actor,
        )

    table_a = _table(sheet_a, actor)
    with pytest.raises(ValidationError, match="table plan.*run"):
        LegacyMigrationRowPreview.objects.create(
            organization=organization_b,
            run=run_b,
            table_plan=table_a,
            source_sheet_index=0,
            source_row_number=6,
            source_column_start=1,
            source_column_end=8,
            canonical_payload={},
            payload_digest="6" * 64,
            classification=LegacyMigrationRowPreview.Classification.QUARANTINED,
            validation_errors=[],
            source_state_digest="7" * 64,
        )


def test_immutable_evidence_rejects_instance_and_bulk_mutation_or_deletion() -> None:
    actor = _account("immutable-evidence@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Immutable Evidence")
    inventory, run = _inventory_and_run(organization, actor)
    worksheet = _worksheet(run)
    table = _table(worksheet, actor)
    preview = _preview(table)
    job = LegacyMigrationJob.objects.create(
        organization=organization,
        run=run,
        job_kind=LegacyMigrationJob.Kind.APPLY,
        job_sequence=1,
        requested_manifest_digest="d" * 64,
        request_rationale="Synthetic immutable-evidence request.",
        created_by=actor,
    )
    checkpoint = LegacyMigrationCheckpoint.objects.create(
        organization=organization,
        run=run,
        job=job,
        worksheet=worksheet,
        table_plan=table,
        sequence=1,
        first_source_row=6,
        last_source_row=20,
        checkpoint_digest="8" * 64,
    )
    decision = LegacyMigrationDecisionRevision.objects.create(
        organization=organization,
        run=run,
        sequence=1,
        decision=LegacyMigrationDecisionRevision.Decision.APPROVE,
        manifest_digest="9" * 64,
        actor=actor,
        rationale="Synthetic approval evidence.",
    )
    manifest = LegacyMigrationManifest.objects.create(
        organization=organization,
        run=run,
        kind=LegacyMigrationManifest.Kind.DRY_RUN,
        sequence=1,
        digest="0" * 64,
        payload={"synthetic": True},
        created_by=actor,
    )

    immutable_changes: list[tuple[Any, str, Any]] = [
        (inventory, "source_key", "changed"),
        (worksheet, "sheet_name", "Changed"),
        (table, "label", "changed"),
        (preview, "payload_digest", "a" * 64),
        (decision, "rationale", "Changed"),
        (manifest, "digest", "a" * 64),
        (checkpoint, "checkpoint_digest", "a" * 64),
    ]
    for evidence, field_name, changed_value in immutable_changes:
        setattr(evidence, field_name, changed_value)
        with pytest.raises(PermissionDenied, match="immutable|append-only"):
            evidence.save()

    with pytest.raises(PermissionDenied, match="immutable"):
        LegacyMigrationRowPreview.objects.filter(pk=preview.pk).update(payload_digest="a" * 64)
    with pytest.raises(PermissionDenied, match="immutable"):
        LegacyMigrationRowPreview.objects.bulk_create(
            [
                LegacyMigrationRowPreview(
                    organization=organization,
                    run=run,
                    table_plan=table,
                    source_sheet_index=0,
                    source_row_number=7,
                    source_column_start=1,
                    source_column_end=8,
                    canonical_payload={"status": "synthetic"},
                    payload_digest="a" * 64,
                    classification=LegacyMigrationRowPreview.Classification.QUARANTINED,
                    validation_errors=[],
                    source_state_digest="2" * 64,
                )
            ]
        )
    with pytest.raises(PermissionDenied, match="immutable"):
        LegacyMigrationManifest.objects.filter(pk=manifest.pk).delete()
    with pytest.raises(PermissionDenied, match="append-only"):
        decision.delete()


def test_operational_run_job_and_checkpoint_state_can_advance_without_rewriting_evidence() -> None:
    actor = _account("operational-state@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Operational State")
    _, run = _inventory_and_run(organization, actor)
    worksheet = _worksheet(run)
    table = _table(worksheet, actor)
    job = LegacyMigrationJob.objects.create(
        organization=organization,
        run=run,
        job_kind=LegacyMigrationJob.Kind.APPLY,
        job_sequence=1,
        requested_manifest_digest="d" * 64,
        request_rationale="Synthetic operational-state request.",
        created_by=actor,
    )
    checkpoint = LegacyMigrationCheckpoint.objects.create(
        organization=organization,
        run=run,
        job=job,
        worksheet=worksheet,
        table_plan=table,
        sequence=1,
        first_source_row=6,
        last_source_row=20,
        checkpoint_digest="8" * 64,
    )

    run.state = LegacyMigrationRun.State.APPLYING
    run.total_rows = 15
    run.save(update_fields=["state", "total_rows", "updated_at"])
    job.status = LegacyMigrationJob.Status.RUNNING
    job.attempt_count = 1
    job.claim_generation = 1
    job.claim_token = "a" * 64
    job.claim_owner = "synthetic-worker"
    job.heartbeat_at = datetime(2026, 8, 14, tzinfo=datetime_timezone.utc)
    job.lease_expires_at = datetime(2026, 8, 14, 0, 5, tzinfo=datetime_timezone.utc)
    job.save(
        update_fields=[
            "status",
            "attempt_count",
            "claim_generation",
            "claim_token",
            "claim_owner",
            "heartbeat_at",
            "lease_expires_at",
            "updated_at",
        ]
    )
    checkpoint.status = LegacyMigrationCheckpoint.Status.COMMITTED
    checkpoint.total_rows = 15
    checkpoint.completed_at = datetime(2026, 8, 14, tzinfo=datetime_timezone.utc)
    checkpoint.save(update_fields=["status", "total_rows", "completed_at"])

    run.refresh_from_db()
    job.refresh_from_db()
    checkpoint.refresh_from_db()
    assert (run.state, run.total_rows) == (LegacyMigrationRun.State.APPLYING, 15)
    assert (job.status, job.attempt_count) == (LegacyMigrationJob.Status.RUNNING, 1)
    assert (checkpoint.status, checkpoint.total_rows) == (
        LegacyMigrationCheckpoint.Status.COMMITTED,
        15,
    )

    with pytest.raises(PermissionDenied, match="immutable"):
        LegacyMigrationCheckpoint.objects.filter(pk=checkpoint.pk).update(total_rows=0)


def test_run_digests_are_write_once_and_bulk_updates_cannot_bypass_provenance() -> None:
    actor = _account("run-digests@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Run Digests")
    _, run = _inventory_and_run(organization, actor)

    run.state = LegacyMigrationRun.State.CONFIGURED
    run.plan_digest = "1" * 64
    run.source_state_digest = "2" * 64
    run.save(
        update_fields=[
            "state",
            "plan_digest",
            "source_state_digest",
            "updated_at",
        ]
    )

    run.plan_digest = "3" * 64
    with pytest.raises(PermissionDenied, match="immutable"):
        run.save(update_fields=["plan_digest", "updated_at"])

    with pytest.raises(PermissionDenied, match="immutable"):
        LegacyMigrationRun.objects.filter(pk=run.pk).update(dry_run_manifest_digest="4" * 64)


def test_domain_constraints_reject_duplicate_coordinates_and_invalid_regions() -> None:
    actor = _account("constraints@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Constraints")
    _, run = _inventory_and_run(organization, actor)
    worksheet = _worksheet(run)
    table = _table(worksheet, actor)

    with pytest.raises(ValidationError, match="end row"):
        LegacyTablePlan.objects.create(
            organization=organization,
            run=run,
            worksheet=worksheet,
            label="invalid",
            header_row=5,
            start_row=10,
            end_row=9,
            start_column=1,
            end_column=8,
            mapping_rules={},
            mapping_digest="7" * 64,
            created_by=actor,
        )

    with transaction.atomic(), pytest.raises((ValidationError, IntegrityError)):
        _worksheet(run, index=0, name="Duplicate Index")
    with transaction.atomic(), pytest.raises((ValidationError, IntegrityError)):
        _worksheet(run, index=2, name="Synthetic Qualifiers")

    _preview(table, source_row=6)
    with transaction.atomic(), pytest.raises((ValidationError, IntegrityError)):
        _preview(table, source_row=6)

    job = LegacyMigrationJob.objects.create(
        organization=organization,
        run=run,
        job_kind=LegacyMigrationJob.Kind.APPLY,
        job_sequence=1,
        requested_manifest_digest="d" * 64,
        request_rationale="Synthetic constraint-validation request.",
        created_by=actor,
    )
    LegacyMigrationCheckpoint.objects.create(
        organization=organization,
        run=run,
        job=job,
        worksheet=worksheet,
        table_plan=table,
        sequence=1,
        first_source_row=6,
        last_source_row=20,
        checkpoint_digest="8" * 64,
    )
    with transaction.atomic(), pytest.raises((ValidationError, IntegrityError)):
        LegacyMigrationCheckpoint.objects.create(
            organization=organization,
            run=run,
            job=job,
            worksheet=worksheet,
            table_plan=table,
            sequence=1,
            first_source_row=21,
            last_source_row=30,
            checkpoint_digest="9" * 64,
        )
    with transaction.atomic(), pytest.raises((ValidationError, IntegrityError)):
        LegacyMigrationCheckpoint.objects.create(
            organization=organization,
            run=run,
            job=job,
            worksheet=worksheet,
            table_plan=table,
            sequence=2,
            first_source_row=6,
            last_source_row=20,
            checkpoint_digest="0" * 64,
        )
