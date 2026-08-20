from __future__ import annotations

import csv
import hashlib
import json
from io import BytesIO, StringIO

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from openpyxl import Workbook

from mnemex.accounts.models import Account, PrivilegedRoleAssignment
from mnemex.foundation.services import IdempotencyConflict
from mnemex.partners.models import PartnerOrganization
from mnemex.people.models import Alias, Person
from mnemex.results.models import (
    IngestionRun,
    MappingTemplate,
    PublishedSourceResult,
    ReconciliationCase,
    SourceArtifact,
    StagedResult,
)
from mnemex.results.services import ingest_manual_rows, ingest_spreadsheet_bytes
from tests.mfa_helpers import enroll_account_mfa

pytestmark = pytest.mark.django_db


def _account(email: str, *, results_manager: bool = True) -> Account:
    account = Account.objects.create_user(email=email, password="synthetic-password-123")
    if results_manager:
        enroll_account_mfa(account)
        PrivilegedRoleAssignment.objects.create(
            account=account,
            role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
            assigned_by=account,
        )
    return account


def _mapping(
    organization: PartnerOrganization, actor: Account, *, exclude_field: str | None = None
) -> MappingTemplate:
    field_map = {
        "source_result_id": "result_id",
        "source_revision": "revision",
        "source_event_id": "event_id",
        "event_name": "event_name",
        "result_date": "result_date",
        "competitor_name": "competitor",
        "discipline": "event",
        "score_type": "score_kind",
        "score": "result",
        "heat_id": "heat_id",
        "wood_species": "wood_species",
        "wood_diameter_mm": "wood_diameter_mm",
        "wood_quality": "wood_quality",
    }
    if exclude_field is not None:
        field_map.pop(exclude_field)
    return MappingTemplate.objects.create(
        organization=organization,
        name="synthetic standard",
        version=1,
        field_map=field_map,
        created_by=actor,
    )


def _valid_row(result_id: str = "result-1", score: object = "12.34") -> dict[str, object]:
    return {
        "result_id": result_id,
        "revision": 1,
        "event_id": "synthetic-show-2026",
        "event_name": "Synthetic Summer Show",
        "result_date": "2026-07-18",
        "competitor": "Synthetic Competitor",
        "event": "UNDERHAND",
        "score_kind": "time",
        "result": score,
        "heat_id": "heat-1",
        "wood_species": "white pine",
        "wood_diameter_mm": "325",
        "wood_quality": "8",
    }


def _csv_bytes(rows: list[dict[str, object]]) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _xlsx_bytes(rows: list[dict[str, object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    headers = list(rows[0])
    sheet.append(headers)
    for row in rows:
        sheet.append([row[column] for column in headers])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_results_ingestion_requires_mfa_bound_results_manager() -> None:
    actor = _account("unauthorized@mnemex.example.invalid", results_manager=False)
    organization = PartnerOrganization.objects.create(name="Synthetic Unauthorized Show")
    mapping = _mapping(organization, actor)

    with pytest.raises(PermissionDenied, match="results manager"):
        ingest_manual_rows(
            actor=actor,
            organization=organization,
            mapping_template=mapping,
            operator_key="unauthorized-1",
            rows=[_valid_row()],
        )

    assert SourceArtifact.objects.count() == 0
    assert IngestionRun.objects.count() == 0


def test_results_ingestion_enforces_the_target_organization_role_scope() -> None:
    actor = _account("scoped-results@mnemex.example.invalid", results_manager=False)
    enroll_account_mfa(actor)
    organization_a = PartnerOrganization.objects.create(name="Synthetic Scoped Results Show A")
    organization_b = PartnerOrganization.objects.create(name="Synthetic Scoped Results Show B")
    PrivilegedRoleAssignment.objects.create(
        account=actor,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        assigned_by=actor,
        scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
        organization=organization_a,
    )
    mapping_a = _mapping(organization_a, actor)
    mapping_b = _mapping(organization_b, actor)

    allowed = ingest_manual_rows(
        actor=actor,
        organization=organization_a,
        mapping_template=mapping_a,
        operator_key="scoped-allow",
        rows=[_valid_row("scoped-allow")],
    )
    assert allowed.run.organization_id == organization_a.pk

    with pytest.raises(PermissionDenied, match="results manager"):
        ingest_manual_rows(
            actor=actor,
            organization=organization_b,
            mapping_template=mapping_b,
            operator_key="scoped-deny",
            rows=[_valid_row("scoped-deny")],
        )

    assert IngestionRun.objects.filter(organization=organization_b).count() == 0


def test_manual_mixed_batch_publishes_valid_and_quarantines_invalid_rows() -> None:
    actor = _account("manual@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Manual Show")
    mapping = _mapping(organization, actor)
    invalid = _valid_row("result-invalid", score="not-a-number")

    outcome = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="manual-mixed-1",
        rows=[_valid_row(), invalid],
    )

    outcome.run.refresh_from_db()
    assert outcome.replayed is False
    assert (outcome.run.total_rows, outcome.run.published_rows, outcome.run.quarantined_rows) == (
        2,
        1,
        1,
    )
    assert outcome.run.status == IngestionRun.Status.COMPLETED_WITH_QUARANTINE
    assert outcome.run.artifact.kind == SourceArtifact.Kind.MANUAL_MANIFEST
    assert outcome.run.artifact.content_type == "application/vnd.mnemex.manual+json"
    assert outcome.run.artifact.digest
    assert outcome.run.artifact.object_reference == ""
    assert PublishedSourceResult.objects.filter(source_result_id="result-1").count() == 1
    invalid_stage = StagedResult.objects.get(source_result_id="result-invalid")
    assert invalid_stage.outcome == StagedResult.Outcome.QUARANTINED
    assert invalid_stage.validation_errors == [
        {"field": "score", "code": "invalid_number", "message": "Enter a numeric score."}
    ]


def test_mapping_requires_portable_career_metadata() -> None:
    actor = _account("missing-mapping@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Missing Mapping Show")
    mapping = _mapping(organization, actor, exclude_field="source_event_id")

    with pytest.raises(ValidationError, match="source_event_id"):
        ingest_manual_rows(
            actor=actor,
            organization=organization,
            mapping_template=mapping,
            operator_key="missing-career-field",
            rows=[_valid_row()],
        )


def test_published_payload_contains_career_and_optional_wood_metadata() -> None:
    actor = _account("career-payload@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Career Payload Show")
    mapping = _mapping(organization, actor)

    outcome = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="career-payload",
        rows=[_valid_row()],
    )

    payload = PublishedSourceResult.objects.get(staged_result__run=outcome.run).normalized_payload
    assert payload == {
        "source_result_id": "result-1",
        "source_revision": 1,
        "source_event_id": "synthetic-show-2026",
        "event_name": "Synthetic Summer Show",
        "result_date": "2026-07-18",
        "competitor_name": "Synthetic Competitor",
        "discipline": "UNDERHAND",
        "score_type": "time",
        "score": "12.34",
        "heat_id": "heat-1",
        "wood_species": "white pine",
        "wood_diameter_mm": 325,
        "wood_quality": 8,
    }


@pytest.mark.parametrize(
    ("updates", "expected_error"),
    [
        ({"event_id": ""}, ("source_event_id", "required")),
        ({"event_name": ""}, ("event_name", "required")),
        ({"result_date": "07/18/2026"}, ("result_date", "invalid_date")),
        ({"event_id": "event\nidentifier"}, ("source_event_id", "invalid_text")),
        ({"event_name": "event\x00name"}, ("event_name", "invalid_text")),
        ({"result_id": "r" * 201}, ("source_result_id", "invalid_text")),
        ({"event_id": "e" * 201}, ("source_event_id", "invalid_text")),
        ({"event_name": "n" * 241}, ("event_name", "invalid_text")),
        ({"competitor": "c" * 241}, ("competitor_name", "invalid_text")),
        ({"heat_id": "h" * 201}, ("heat_id", "invalid_text")),
        ({"wood_species": "w" * 161}, ("wood_species", "invalid_text")),
        ({"wood_diameter_mm": "0"}, ("wood_diameter_mm", "invalid_positive_integer")),
        ({"wood_diameter_mm": 0}, ("wood_diameter_mm", "invalid_positive_integer")),
        ({"wood_diameter_mm": "325.5"}, ("wood_diameter_mm", "invalid_positive_integer")),
        ({"wood_quality": "0"}, ("wood_quality", "out_of_range")),
        ({"wood_quality": "11"}, ("wood_quality", "out_of_range")),
        ({"result": "0"}, ("score", "must_be_positive")),
        ({"result": "-0.01"}, ("score", "must_be_positive")),
    ],
)
def test_invalid_career_metadata_and_time_scores_are_quarantined(
    updates: dict[str, object], expected_error: tuple[str, str]
) -> None:
    case_id = hashlib.sha256(repr(sorted(updates.items())).encode("utf-8")).hexdigest()[:12]
    actor = _account(f"invalid-{case_id}@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name=f"Synthetic Invalid {case_id}")
    mapping = _mapping(organization, actor)
    row = _valid_row()
    row.update(updates)

    outcome = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key=f"invalid-{case_id}",
        rows=[row],
    )

    staged = StagedResult.objects.get(run=outcome.run)
    assert staged.outcome == StagedResult.Outcome.QUARANTINED
    assert expected_error in {(error["field"], error["code"]) for error in staged.validation_errors}


def test_invalid_nul_is_quarantined_with_jsonb_safe_diagnostics_and_exact_artifact_digest() -> None:
    actor = _account("invalid-nul@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Invalid NUL")
    mapping = _mapping(organization, actor)
    row = _valid_row()
    row["event_name"] = "event\x00name"
    source_manifest = json.dumps([row], sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )

    outcome = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="invalid-nul",
        rows=[row],
    )

    staged = StagedResult.objects.get(run=outcome.run)
    assert staged.outcome == StagedResult.Outcome.QUARANTINED
    assert staged.normalized_payload["event_name"] == "event\\u0000name"
    assert staged.validation_errors == [
        {
            "field": "event_name",
            "code": "invalid_text",
            "message": "Enter plain text of 240 characters or fewer.",
        }
    ]
    assert outcome.run.artifact.digest == hashlib.sha256(source_manifest).hexdigest()
    assert outcome.run.artifact.byte_size == len(source_manifest)
    assert PublishedSourceResult.objects.filter(staged_result=staged).count() == 0


@pytest.mark.parametrize("score_type", ["hits", "distance", "raw_score", "place_only"])
def test_non_time_score_types_allow_zero_but_reject_negative(score_type: str) -> None:
    actor = _account(f"score-{score_type}@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name=f"Synthetic {score_type} Score Show")
    mapping = _mapping(organization, actor)
    zero = _valid_row(f"{score_type}-zero", score=0)
    zero["score_kind"] = score_type
    negative = _valid_row(f"{score_type}-negative", score="-1")
    negative["score_kind"] = score_type

    outcome = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key=f"score-{score_type}",
        rows=[zero, negative],
    )

    assert outcome.run.published_rows == 1
    assert outcome.run.quarantined_rows == 1
    error = StagedResult.objects.get(source_result_id=f"{score_type}-negative")
    assert error.validation_errors == [
        {
            "field": "score",
            "code": "must_be_non_negative",
            "message": "Enter a score of zero or greater.",
        }
    ]


def test_blank_optional_wood_fields_publish_as_null_values() -> None:
    actor = _account("blank-wood@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Blank Wood Show")
    mapping = _mapping(organization, actor)
    row = _valid_row()
    row.update({"heat_id": "", "wood_species": "", "wood_diameter_mm": "", "wood_quality": ""})

    outcome = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="blank-wood",
        rows=[row],
    )

    payload = PublishedSourceResult.objects.get(staged_result__run=outcome.run).normalized_payload
    assert payload["heat_id"] == ""
    assert payload["wood_species"] == ""
    assert payload["wood_diameter_mm"] is None
    assert payload["wood_quality"] is None


def test_csv_and_xlsx_share_mapping_and_provenance_pipeline() -> None:
    actor = _account("files@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic File Show")
    mapping = _mapping(organization, actor)

    csv_outcome = ingest_spreadsheet_bytes(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="csv-1",
        filename="results.csv",
        content_type="text/csv",
        content=_csv_bytes([_valid_row("csv-result")]),
    )
    xlsx_outcome = ingest_spreadsheet_bytes(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="xlsx-1",
        filename="results.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        content=_xlsx_bytes([_valid_row("xlsx-result")]),
    )

    assert csv_outcome.run.artifact.kind == SourceArtifact.Kind.SPREADSHEET
    assert xlsx_outcome.run.artifact.kind == SourceArtifact.Kind.SPREADSHEET
    assert csv_outcome.run.mapping_template_id == xlsx_outcome.run.mapping_template_id
    assert csv_outcome.run.published_rows == xlsx_outcome.run.published_rows == 1
    assert set(PublishedSourceResult.objects.values_list("source_result_id", flat=True)) >= {
        "csv-result",
        "xlsx-result",
    }


def test_exact_retry_is_idempotent_and_changed_payload_cannot_reuse_operator_key() -> None:
    actor = _account("retry@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Retry Show")
    mapping = _mapping(organization, actor)
    content = _csv_bytes([_valid_row("retry-result")])
    call = {
        "actor": actor,
        "organization": organization,
        "mapping_template": mapping,
        "operator_key": "retry-key",
        "filename": "retry.csv",
        "content_type": "text/csv",
    }

    first = ingest_spreadsheet_bytes(content=content, **call)
    second = ingest_spreadsheet_bytes(content=content, **call)

    assert second.replayed is True
    assert second.run.pk == first.run.pk
    assert SourceArtifact.objects.count() == 1
    assert IngestionRun.objects.count() == 1
    assert StagedResult.objects.count() == 1
    assert PublishedSourceResult.objects.count() == 1

    with pytest.raises(IdempotencyConflict):
        ingest_spreadsheet_bytes(
            content=_csv_bytes([_valid_row("retry-result", score="99.99")]), **call
        )


def test_source_identity_duplicate_and_changed_payload_are_non_destructive() -> None:
    actor = _account("conflict@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Conflict Show")
    mapping = _mapping(organization, actor)

    original = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="original",
        rows=[_valid_row("stable-result", score="12.34")],
    )
    duplicates = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="duplicates",
        rows=[_valid_row("duplicate-result"), _valid_row("duplicate-result")],
    )
    conflict = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="conflict",
        rows=[_valid_row("stable-result", score="88.88")],
    )

    assert original.run.published_rows == 1
    assert duplicates.run.published_rows == 1
    assert duplicates.run.duplicate_rows == 1
    assert conflict.run.conflict_rows == 1
    published = PublishedSourceResult.objects.get(
        organization=organization, source_result_id="stable-result", source_revision=1
    )
    assert published.normalized_payload["score"] == "12.34"
    assert ReconciliationCase.objects.filter(
        case_type=ReconciliationCase.CaseType.SOURCE_PAYLOAD_CONFLICT,
        staged_result__run=conflict.run,
    ).exists()
    assert StagedResult.objects.get(run=conflict.run).outcome == StagedResult.Outcome.CONFLICT


def test_matching_name_never_automatically_links_a_person() -> None:
    actor = _account("identity@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Identity Show")
    mapping = _mapping(organization, actor)
    person = Person.objects.create()
    Alias.objects.create(
        person=person,
        value="Synthetic Competitor",
        normalized_value="synthetic competitor",
        source="synthetic-test",
        review_state=Alias.ReviewState.APPROVED,
    )

    outcome = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="identity-unresolved",
        rows=[_valid_row("identity-result")],
    )

    published = PublishedSourceResult.objects.get(staged_result__run=outcome.run)
    assert published.person_id is None
    assert ReconciliationCase.objects.filter(
        case_type=ReconciliationCase.CaseType.IDENTITY_UNRESOLVED,
        staged_result__run=outcome.run,
    ).exists()


def test_published_source_results_are_immutable() -> None:
    actor = _account("immutable@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Immutable Show")
    mapping = _mapping(organization, actor)
    outcome = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="immutable",
        rows=[_valid_row("immutable-result")],
    )
    published = PublishedSourceResult.objects.get(staged_result__run=outcome.run)
    published.normalized_payload = {"score": "0.01"}

    with pytest.raises(PermissionDenied, match="immutable"):
        published.save()
    with pytest.raises(PermissionDenied, match="immutable"):
        PublishedSourceResult.objects.filter(pk=published.pk).delete()


def test_ingestion_provenance_is_append_only_and_tenant_relationships_fail_closed() -> None:
    actor = _account("provenance-tenant@mnemex.example.invalid")
    organization_a = PartnerOrganization.objects.create(name="Synthetic Provenance A")
    organization_b = PartnerOrganization.objects.create(name="Synthetic Provenance B")
    mapping_a = _mapping(organization_a, actor)
    mapping_b = _mapping(organization_b, actor)
    artifact_a = SourceArtifact.objects.create(
        organization=organization_a,
        kind=SourceArtifact.Kind.SPREADSHEET,
        digest="a" * 64,
        original_name="synthetic-a.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        byte_size=10,
        object_reference="synthetic/a.xlsx",
        uploaded_by=actor,
    )
    artifact_b = SourceArtifact.objects.create(
        organization=organization_b,
        kind=SourceArtifact.Kind.SPREADSHEET,
        digest="b" * 64,
        original_name="synthetic-b.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        byte_size=10,
        object_reference="synthetic/b.xlsx",
        uploaded_by=actor,
    )
    digest_b = hashlib.sha256(
        json.dumps(mapping_b.field_map, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    with pytest.raises(ValidationError, match="artifact organization"):
        IngestionRun.objects.create(
            organization=organization_a,
            artifact=artifact_b,
            mapping_template=mapping_a,
            field_map_digest=hashlib.sha256(
                json.dumps(mapping_a.field_map, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            operator_key="cross-artifact",
            request_digest="1" * 64,
            created_by=actor,
        )
    with pytest.raises(ValidationError, match="mapping organization"):
        IngestionRun.objects.create(
            organization=organization_a,
            artifact=artifact_a,
            mapping_template=mapping_b,
            field_map_digest=digest_b,
            operator_key="cross-mapping",
            request_digest="2" * 64,
            created_by=actor,
        )

    run_b = IngestionRun.objects.create(
        organization=organization_b,
        artifact=artifact_b,
        mapping_template=mapping_b,
        field_map_digest=digest_b,
        operator_key="tenant-b",
        request_digest="3" * 64,
        created_by=actor,
    )
    payload = {
        "source_result_id": "tenant-b-result",
        "source_revision": 1,
        "discipline": "UNDERHAND",
        "score_type": "time",
        "score": "12.3",
    }
    payload_digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    staged_b = StagedResult.objects.create(
        run=run_b,
        row_number=1,
        source_result_id="tenant-b-result",
        source_revision=1,
        normalized_payload=payload,
        payload_digest=payload_digest,
        validation_errors=[],
        outcome=StagedResult.Outcome.PUBLISHED,
    )
    with pytest.raises(ValidationError, match="staged result organization"):
        PublishedSourceResult.objects.create(
            organization=organization_a,
            source_result_id="tenant-b-result",
            source_revision=1,
            discipline="UNDERHAND",
            score_type="time",
            normalized_payload=payload,
            payload_digest=payload_digest,
            artifact=artifact_a,
            staged_result=staged_b,
        )

    outcome = ingest_manual_rows(
        actor=actor,
        organization=organization_a,
        mapping_template=mapping_a,
        operator_key="immutable-provenance",
        rows=[_valid_row("immutable-provenance")],
    )
    ingestion = outcome.run
    staged = ingestion.staged_results.get()
    ingestion.request_digest = "4" * 64
    with pytest.raises(PermissionDenied, match="immutable"):
        ingestion.save()
    with pytest.raises(PermissionDenied, match="immutable"):
        IngestionRun.objects.filter(pk=ingestion.pk).update(request_digest="5" * 64)
    staged.outcome = StagedResult.Outcome.CONFLICT
    with pytest.raises(PermissionDenied, match="immutable"):
        staged.save()
    with pytest.raises(PermissionDenied, match="immutable"):
        StagedResult.objects.filter(pk=staged.pk).update(outcome=StagedResult.Outcome.CONFLICT)


def test_source_revisions_are_bounded_contiguous_and_linked() -> None:
    actor = _account("revision-chain@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Revision Chain Show")
    mapping = _mapping(organization, actor)

    first = _valid_row("corrected-result", score="12.34")
    revision_three = _valid_row("corrected-result", score="10.00")
    revision_three["revision"] = 3
    out_of_order = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="revision-three-before-two",
        rows=[revision_three],
    )

    assert out_of_order.run.published_rows == 0
    assert out_of_order.run.quarantined_rows == 1
    assert StagedResult.objects.get(run=out_of_order.run).validation_errors == [
        {
            "field": "source_revision",
            "code": "noncontiguous_revision",
            "message": "Revision 3 requires published revision 2 for this source result.",
        }
    ]

    ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="revision-one",
        rows=[first],
    )
    revision_two = _valid_row("corrected-result", score="11.00")
    revision_two["revision"] = 2
    corrected = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="revision-two",
        rows=[revision_two],
    )

    published = list(
        PublishedSourceResult.objects.filter(source_result_id="corrected-result").order_by(
            "source_revision"
        )
    )
    assert corrected.run.published_rows == 1
    assert [result.source_revision for result in published] == [1, 2]
    assert published[1].predecessor_id == published[0].pk


def test_source_revision_above_postgresql_integer_range_is_quarantined() -> None:
    actor = _account("revision-bound@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Revision Bound Show")
    mapping = _mapping(organization, actor)
    row = _valid_row("revision-overflow")
    row["revision"] = 2_147_483_648

    outcome = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="revision-overflow",
        rows=[row],
    )

    assert outcome.run.quarantined_rows == 1
    assert StagedResult.objects.get(run=outcome.run).validation_errors == [
        {
            "field": "source_revision",
            "code": "invalid_revision",
            "message": "Enter a revision from 1 to 2147483647.",
        }
    ]


@pytest.mark.parametrize("score", ["1e-999999999", "9" * 65])
def test_pathological_numeric_expansion_is_quarantined(score: str) -> None:
    actor = _account(
        f"numeric-bound-{hashlib.sha256(score.encode()).hexdigest()[:8]}@mnemex.example.invalid"
    )
    organization = PartnerOrganization.objects.create(name=f"Synthetic Numeric Bound {len(score)}")
    mapping = _mapping(organization, actor)

    outcome = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key=f"numeric-bound-{len(score)}",
        rows=[_valid_row("numeric-bound", score=score)],
    )

    staged = StagedResult.objects.get(run=outcome.run)
    assert outcome.run.quarantined_rows == 1
    assert staged.validation_errors == [
        {
            "field": "score",
            "code": "number_out_of_bounds",
            "message": "Enter a score with at most 64 significant digits and 128 fixed-point characters.",
        }
    ]


def test_pathological_optional_integer_expansion_is_quarantined() -> None:
    actor = _account("integer-bound@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Integer Bound")
    mapping = _mapping(organization, actor)
    row = _valid_row("integer-bound")
    row["wood_diameter_mm"] = "1e999999999"

    outcome = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="integer-bound",
        rows=[row],
    )

    assert outcome.run.quarantined_rows == 1
    assert StagedResult.objects.get(run=outcome.run).validation_errors == [
        {
            "field": "wood_diameter_mm",
            "code": "invalid_positive_integer",
            "message": "Enter a whole-number wood diameter greater than zero, or leave it blank.",
        }
    ]


@pytest.mark.parametrize(
    "content",
    [
        b"result_id,result_id,revision\na,b,1\n",
        b"result_id,,revision\na,b,1\n",
        b"result_id,revision\na,1,unexpected\n",
    ],
)
def test_csv_rejects_duplicate_blank_and_overflow_headers(content: bytes) -> None:
    actor = _account(
        f"csv-headers-{hashlib.sha256(content).hexdigest()[:8]}@mnemex.example.invalid"
    )
    organization = PartnerOrganization.objects.create(name="Synthetic CSV Header Guard")

    with pytest.raises(ValidationError, match="header|more values"):
        ingest_spreadsheet_bytes(
            actor=actor,
            organization=organization,
            mapping_template=_mapping(organization, actor),
            operator_key=f"csv-headers-{hashlib.sha256(content).hexdigest()[:8]}",
            filename="synthetic.csv",
            content_type="text/csv",
            content=content,
        )

    assert SourceArtifact.objects.count() == 0


def test_xlsx_rejects_duplicate_headers() -> None:
    actor = _account("xlsx-headers@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic XLSX Header Guard")
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["result_id", "result_id", "revision"])
    sheet.append(["a", "b", 1])
    buffer = BytesIO()
    workbook.save(buffer)

    with pytest.raises(ValidationError, match="header names must be unique"):
        ingest_spreadsheet_bytes(
            actor=actor,
            organization=organization,
            mapping_template=_mapping(organization, actor),
            operator_key="xlsx-duplicate-headers",
            filename="synthetic.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            content=buffer.getvalue(),
        )


def test_provenance_records_are_immutable_and_ingestion_pins_mapping_digest() -> None:
    actor = _account("provenance@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Provenance Show")
    mapping = _mapping(organization, actor)
    expected_mapping_digest = hashlib.sha256(
        json.dumps(
            mapping.field_map,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    outcome = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="provenance",
        rows=[_valid_row("provenance")],
    )

    assert outcome.run.field_map_digest == expected_mapping_digest
    mapping.field_map = {"source_result_id": "wrong"}
    with pytest.raises(PermissionDenied, match="immutable"):
        mapping.save()
    MappingTemplate.objects.filter(pk=mapping.pk).update(is_active=False)
    mapping.refresh_from_db()
    assert mapping.is_active is False

    artifact = outcome.run.artifact
    artifact.original_name = "mutated.csv"
    with pytest.raises(PermissionDenied, match="immutable"):
        artifact.save()
    with pytest.raises(PermissionDenied, match="immutable"):
        SourceArtifact.objects.filter(pk=artifact.pk).update(original_name="mutated.csv")
