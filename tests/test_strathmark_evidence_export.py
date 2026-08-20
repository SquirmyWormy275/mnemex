from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Any
from unittest import mock

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from mnemex.accounts.models import Account, PrivilegedRoleAssignment
from mnemex.career.models import CareerAssertionRevision
from mnemex.export import services as export_services
from mnemex.export.adapters import StoredEvidenceSnapshotSource
from mnemex.export.contract import (
    EVIDENCE_HISTORY_ROW_SCHEMA_VERSION,
    EVIDENCE_SNAPSHOT_SOURCE_SCHEMA_VERSION,
)
from mnemex.export.models import EvidenceSnapshotManifest, ExportEligibilityRevision
from mnemex.export.services import generate_evidence_snapshot, review_export_eligibility
from mnemex.export.views import _current_assertions
from mnemex.foundation.models import AuditEvent, IdempotencyRecord
from mnemex.foundation.services import IdempotencyConflict
from mnemex.partners.models import PartnerOrganization
from mnemex.people.models import Person
from mnemex.results.models import (
    IngestionRun,
    MappingTemplate,
    PublishedSourceResult,
    ReconciliationCase,
    SourceArtifact,
    StagedResult,
)
from mnemex.schema import Discipline, ScoreType
from tests.mfa_helpers import enroll_account_mfa

pytestmark = pytest.mark.django_db
UTC = dt_timezone.utc
CUTOFF = date(2026, 8, 2)
CAPTURED_AT = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)


def test_export_contract_versions_match_strathmark_2() -> None:
    assert EVIDENCE_SNAPSHOT_SOURCE_SCHEMA_VERSION == "strathmark.evidence-snapshot-source.v1"
    assert EVIDENCE_HISTORY_ROW_SCHEMA_VERSION == "strathmark.evidence-history-row.v1"


def _reviewer(
    label: str,
    organization: PartnerOrganization,
    *,
    with_role: bool = True,
    with_mfa: bool = True,
) -> Account:
    actor = Account.objects.create_user(
        email=f"{label}-{uuid.uuid4()}@mnemex.example.invalid",
        password="synthetic-password-123",
    )
    if with_mfa:
        enroll_account_mfa(actor)
    if with_role:
        PrivilegedRoleAssignment.objects.create(
            account=actor,
            role=PrivilegedRoleAssignment.Role.EXPORT_REVIEWER,
            scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
            organization=organization,
            assigned_by=actor,
        )
    return actor


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _career_assertion_unfrozen(
    *,
    organization: PartnerOrganization,
    actor: Account,
    label: str,
    discipline: Discipline = Discipline.UNDERHAND,
    score_type: ScoreType = ScoreType.TIME,
    score: object = "12.34",
    result_date: object = "2026-07-18",
    source_event_id: object = "show-2026",
    heat_id: object = "heat-1",
    wood_species: object = "white_pine",
    wood_diameter_mm: object = 325,
    wood_quality: object = 8,
    person: Person | None = None,
    source_result_id: str | None = None,
    source_revision: int = 1,
    source_predecessor: PublishedSourceResult | None = None,
) -> CareerAssertionRevision:
    digest = _digest(label)
    artifact = SourceArtifact.objects.create(
        organization=organization,
        kind=SourceArtifact.Kind.MANUAL_MANIFEST,
        digest=digest,
        original_name="synthetic-manual-entry.json",
        content_type="application/vnd.mnemex.manual+json",
        byte_size=128,
        uploaded_by=actor,
    )
    mapping = MappingTemplate.objects.create(
        organization=organization,
        name=f"synthetic-{label}",
        version=1,
        field_map={"synthetic": "synthetic"},
        created_by=actor,
    )
    run = IngestionRun.objects.create(
        organization=organization,
        artifact=artifact,
        mapping_template=mapping,
        operator_key=f"synthetic-{label}",
        request_digest=digest,
        created_by=actor,
    )
    result_id = source_result_id or f"result-{label}"
    payload = {
        "source_result_id": result_id,
        "source_revision": source_revision,
        "source_event_id": source_event_id,
        "event_name": "Synthetic Show",
        "result_date": result_date,
        "competitor_name": f"Secret Name {label}",
        "discipline": discipline.value,
        "score_type": score_type.value,
        "score": score,
        "heat_id": heat_id,
        "wood_species": wood_species,
        "wood_diameter_mm": wood_diameter_mm,
        "wood_quality": wood_quality,
    }
    staged = StagedResult.objects.create(
        run=run,
        row_number=1,
        source_result_id=result_id,
        source_revision=source_revision,
        normalized_payload=payload,
        payload_digest=digest,
        validation_errors=[],
        outcome=StagedResult.Outcome.PUBLISHED,
        proposed_person_ids=[],
    )
    published = PublishedSourceResult.objects.create(
        organization=organization,
        source_result_id=result_id,
        source_revision=source_revision,
        discipline=discipline.value,
        score_type=score_type.value,
        normalized_payload=payload,
        payload_digest=digest,
        artifact=artifact,
        staged_result=staged,
        predecessor=source_predecessor,
    )
    case = ReconciliationCase.objects.create(
        case_type=ReconciliationCase.CaseType.IDENTITY_UNRESOLVED,
        status=ReconciliationCase.Status.RESOLVED,
        staged_result=staged,
        existing_published_result=published,
        details={"reason": "synthetic"},
        resolved_by=actor,
        resolved_at=timezone.now(),
    )
    run.status = IngestionRun.Status.COMPLETED
    run.total_rows = 1
    run.published_rows = 1
    run.completed_at = timezone.now()
    run.save()
    person = person or Person.objects.create()
    return CareerAssertionRevision.objects.create(
        organization=organization,
        source_result=published,
        person=person,
        reconciliation_case=case,
        revision=1,
        decision=CareerAssertionRevision.Decision.APPROVE_LINK,
        authorization_basis_type=CareerAssertionRevision.AuthorizationBasis.SOURCE_DATA_RIGHTS,
        authorization_basis_reference="synthetic-policy:results-rights:v1",
        authorization_captured_at=timezone.now(),
        reviewed_by=actor,
        source_payload_digest=digest,
        decision_digest=digest,
    )


def _career_assertion(**kwargs: Any) -> CareerAssertionRevision:
    """Create normal fixture history before the fixed historical capture time."""
    with mock.patch("django.utils.timezone.now", return_value=CAPTURED_AT - timedelta(hours=1)):
        return _career_assertion_unfrozen(**kwargs)


def _review(
    assertion: CareerAssertionRevision,
    actor: Account,
    *,
    decision: str = ExportEligibilityRevision.Decision.ELIGIBLE,
    key: str | None = None,
):
    with mock.patch("django.utils.timezone.now", return_value=CAPTURED_AT - timedelta(minutes=30)):
        return review_export_eligibility(
            actor=actor,
            organization=assertion.organization,
            career_assertion=assertion,
            decision=decision,
            reason="Reviewed against synthetic STRATHMARK policy",
            operator_key=key or f"review-{assertion.pk}-{decision}",
        )


def _snapshot(
    actor: Account,
    organization: PartnerOrganization,
    *,
    source_id: str = "mnemex:snapshot:synthetic-2026-08-02",
    key: str = "snapshot-synthetic-2026-08-02",
):
    return generate_evidence_snapshot(
        actor=actor,
        organization=organization,
        source_id=source_id,
        cutoff=CUTOFF,
        captured_at=CAPTURED_AT,
        operator_key=key,
    )


def test_export_review_requires_mfa_role_and_matching_organization() -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Export Scope")
    wrong_organization = PartnerOrganization.objects.create(name="Synthetic Wrong Scope")
    creator = _reviewer("creator", organization)
    assertion = _career_assertion(organization=organization, actor=creator, label="authorization")

    for denied in (
        _reviewer("no-role", organization, with_role=False),
        _reviewer("no-mfa", organization, with_mfa=False),
        _reviewer("wrong-org", wrong_organization),
    ):
        with pytest.raises(PermissionDenied, match="export reviewer"):
            review_export_eligibility(
                actor=denied,
                organization=organization,
                career_assertion=assertion,
                decision=ExportEligibilityRevision.Decision.ELIGIBLE,
                reason="Synthetic denied review",
                operator_key=f"denied-{denied.pk}",
            )

    assert ExportEligibilityRevision.objects.count() == 0


def test_eligibility_is_append_only_idempotent_and_correction_based() -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Eligibility History")
    actor = _reviewer("eligibility", organization)
    assertion = _career_assertion(organization=organization, actor=actor, label="history")

    first = _review(assertion, actor, key="eligibility-first")
    replay = _review(assertion, actor, key="eligibility-first")
    corrected = _review(
        assertion,
        actor,
        decision=ExportEligibilityRevision.Decision.REJECTED,
        key="eligibility-correction",
    )

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.revision.pk == first.revision.pk
    assert first.revision.revision == 1
    assert corrected.revision.revision == 2
    assert corrected.revision.predecessor_id == first.revision.pk
    assert first.revision.is_current is False
    assert corrected.revision.is_current is True
    assert corrected.revision.decision == ExportEligibilityRevision.Decision.REJECTED
    with pytest.raises(PermissionDenied, match="immutable"):
        ExportEligibilityRevision.objects.filter(pk=first.revision.pk).delete()

    with pytest.raises(IdempotencyConflict):
        _review(
            assertion,
            actor,
            decision=ExportEligibilityRevision.Decision.ELIGIBLE,
            key="eligibility-correction",
        )

    event = AuditEvent.objects.get(
        action="export.eligibility_reviewed", target_id=str(first.revision.pk)
    )
    assert event.metadata["organization_id"] == str(organization.pk)
    assert "competitor_name" not in str(event.metadata)


def test_only_reviewed_current_valid_sb_uh_rows_export_and_exclusions_are_visible() -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Snapshot Selection")
    actor = _reviewer("selection", organization)
    valid_uh = _career_assertion(organization=organization, actor=actor, label="valid-uh")
    valid_sb = _career_assertion(
        organization=organization,
        actor=actor,
        label="valid-sb",
        discipline=Discipline.STANDING_BLOCK,
        score="48.50",
    )
    unreviewed = _career_assertion(organization=organization, actor=actor, label="unreviewed")
    unsupported = _career_assertion(
        organization=organization,
        actor=actor,
        label="single-buck",
        discipline=Discipline.SINGLE_BUCK,
    )
    post_cutoff = _career_assertion(
        organization=organization,
        actor=actor,
        label="post-cutoff",
        result_date=CUTOFF.isoformat(),
    )
    incomplete = _career_assertion(
        organization=organization,
        actor=actor,
        label="incomplete",
        wood_species=None,
        wood_diameter_mm=None,
        wood_quality=None,
    )
    rejected = _career_assertion(organization=organization, actor=actor, label="review-rejected")
    superseded = _career_assertion(organization=organization, actor=actor, label="superseded")

    for assertion in (valid_uh, valid_sb, post_cutoff, superseded):
        _review(assertion, actor)
    with mock.patch("django.utils.timezone.now", return_value=CAPTURED_AT - timedelta(minutes=20)):
        for legacy_invalid in (unsupported, incomplete):
            ExportEligibilityRevision.objects.create(
                organization=organization,
                career_assertion=legacy_invalid,
                revision=1,
                decision=ExportEligibilityRevision.Decision.ELIGIBLE,
                reason="Synthetic pre-hardening eligibility record",
                reviewed_by=actor,
                decision_digest=_digest(f"legacy-{legacy_invalid.pk}"),
            )
    _review(rejected, actor, decision=ExportEligibilityRevision.Decision.REJECTED)
    with mock.patch("django.utils.timezone.now", return_value=CAPTURED_AT - timedelta(minutes=10)):
        CareerAssertionRevision.objects.create(
            organization=organization,
            source_result=superseded.source_result,
            person=Person.objects.create(),
            reconciliation_case=superseded.reconciliation_case,
            revision=2,
            predecessor=superseded,
            decision=CareerAssertionRevision.Decision.RELINK,
            authorization_basis_type=CareerAssertionRevision.AuthorizationBasis.SOURCE_DATA_RIGHTS,
            authorization_basis_reference="synthetic-policy:corrected-link:v1",
            authorization_captured_at=timezone.now(),
            reviewed_by=actor,
            source_payload_digest=superseded.source_payload_digest,
            decision_digest=_digest("superseded-successor"),
        )

    outcome = _snapshot(actor, organization)

    assert len(outcome.snapshot.rows) == 2
    assert {row["event_code"] for row in outcome.snapshot.rows} == {"SB", "UH"}
    reasons = {item["reason"] for item in outcome.snapshot.exclusions}
    assert {
        "unreviewed",
        "review_rejected",
        "unsupported_discipline",
        "on_or_after_cutoff",
        "missing_wood_metadata",
        "superseded_identity_assertion",
    } <= reasons
    assert unreviewed.pk in {
        uuid.UUID(item["assertion_revision_id"])
        for item in outcome.snapshot.exclusions
        if item["reason"] == "unreviewed"
    }


def test_snapshot_envelope_is_deterministic_pseudonymous_and_contains_no_pii() -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic PII Boundary")
    actor = _reviewer("pii-boundary", organization)
    assertion = _career_assertion(
        organization=organization,
        actor=actor,
        label="pii-boundary",
        source_event_id="source-show-42",
        heat_id="final-heat",
    )
    _review(assertion, actor)

    outcome = _snapshot(actor, organization)
    envelope = outcome.snapshot.envelope
    row = envelope["rows"][0]

    assert envelope == {
        "schema_version": EVIDENCE_SNAPSHOT_SOURCE_SCHEMA_VERSION,
        "source_id": "mnemex:snapshot:synthetic-2026-08-02",
        "cutoff": CUTOFF.isoformat(),
        "cutoff_semantics": "exclusive-utc-date",
        "captured_at": CAPTURED_AT.isoformat(),
        "rows": outcome.snapshot.rows,
        "source_digest": outcome.snapshot.source_digest,
    }
    assert row["schema_version"] == EVIDENCE_HISTORY_ROW_SCHEMA_VERSION
    assert row["competitor_id"].startswith("mnemex:competitor:")
    assert str(assertion.person_id) not in row["competitor_id"]
    assert row["competition_id"].startswith("mnemex:event:")
    assert row["heat_id"].startswith("mnemex:heat:")
    assert row["event_code"] == "UH"
    assert row["time_seconds"] == 12.34
    assert set(row) == {
        "schema_version",
        "competitor_id",
        "event_code",
        "time_seconds",
        "species",
        "diameter_mm",
        "quality",
        "competition_id",
        "heat_id",
        "result_date",
    }
    serialized = str(envelope)
    assert "Secret Name" not in serialized
    assert actor.email not in serialized
    assert "competitor_name" not in serialized
    assert "source-show-42" not in serialized
    assert "final-heat" not in serialized


def test_heat_identity_is_shared_within_source_heat_and_blank_is_preserved() -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Heat Identity")
    actor = _reviewer("heat-identity", organization)
    shared_a = _career_assertion(
        organization=organization,
        actor=actor,
        label="shared-heat-a",
        source_event_id="show-shared",
        heat_id="heat-final",
    )
    shared_b = _career_assertion(
        organization=organization,
        actor=actor,
        label="shared-heat-b",
        source_event_id="show-shared",
        heat_id="heat-final",
    )
    blank = _career_assertion(
        organization=organization,
        actor=actor,
        label="blank-heat",
        source_event_id="show-shared",
        heat_id="",
    )
    for assertion in (shared_a, shared_b, blank):
        _review(assertion, actor)

    rows = _snapshot(actor, organization).snapshot.rows
    heat_ids = {row["competitor_id"]: row["heat_id"] for row in rows}

    assert heat_ids != {}
    shared_heat_ids = {row["heat_id"] for row in rows if row["heat_id"]}
    assert len(shared_heat_ids) == 1
    assert sum(row["heat_id"] == "" for row in rows) == 1


def test_competitor_pseudonym_is_stable_across_organizations_and_hides_person_uuid() -> None:
    first_organization = PartnerOrganization.objects.create(name="Synthetic Org One")
    second_organization = PartnerOrganization.objects.create(name="Synthetic Org Two")
    first_actor = _reviewer("cross-org-one", first_organization)
    second_actor = _reviewer("cross-org-two", second_organization)
    person = Person.objects.create()
    first = _career_assertion(
        organization=first_organization,
        actor=first_actor,
        label="cross-org-one",
        person=person,
    )
    second = _career_assertion(
        organization=second_organization,
        actor=second_actor,
        label="cross-org-two",
        person=person,
    )
    _review(first, first_actor)
    _review(second, second_actor)

    first_id = _snapshot(first_actor, first_organization).snapshot.rows[0]["competitor_id"]
    second_id = _snapshot(
        second_actor,
        second_organization,
        source_id="mnemex:snapshot:synthetic-org-two",
        key="snapshot-synthetic-org-two",
    ).snapshot.rows[0]["competitor_id"]

    assert first_id == second_id
    assert first_id.startswith("mnemex:competitor:")
    assert str(person.pk) not in first_id


@pytest.mark.parametrize(
    ("field_overrides", "expected_message"),
    [
        ({"discipline": Discipline.SINGLE_BUCK}, "unsupported discipline"),
        ({"score_type": ScoreType.RAW_SCORE}, "time-scored"),
        ({"score": "nan"}, "score must be finite"),
        ({"score": "2.99"}, "between 3 and 180"),
        ({"score": "180.01"}, "between 3 and 180"),
        ({"result_date": ""}, "include a result date"),
        ({"result_date": "07/18/2026"}, "valid ISO date"),
        ({"result_date": (timezone.now().date() + timedelta(days=1)).isoformat()}, "future"),
        ({"wood_species": "white pine"}, "species"),
        ({"wood_diameter_mm": 224}, "diameter"),
        ({"wood_diameter_mm": 325.5}, "diameter"),
        ({"wood_quality": 11}, "quality"),
        ({"wood_quality": 8.5}, "quality"),
        ({"source_event_id": ""}, "source event"),
    ],
)
def test_eligible_review_fails_closed_for_nonexportable_current_assertion(
    field_overrides: dict[str, object], expected_message: str
) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Closed Review")
    actor = _reviewer("closed-review", organization)
    assertion = _career_assertion(
        organization=organization,
        actor=actor,
        label=f"closed-{expected_message}-{uuid.uuid4()}",
        **field_overrides,
    )

    with pytest.raises(ValidationError, match=expected_message):
        _review(assertion, actor)

    assert ExportEligibilityRevision.objects.count() == 0


def test_rejected_review_remains_available_for_nonexportable_current_assertion() -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Rejection")
    actor = _reviewer("rejection", organization)
    assertion = _career_assertion(
        organization=organization,
        actor=actor,
        label="rejected-unsupported",
        discipline=Discipline.SINGLE_BUCK,
    )

    outcome = _review(
        assertion,
        actor,
        decision=ExportEligibilityRevision.Decision.REJECTED,
    )

    assert outcome.revision.decision == ExportEligibilityRevision.Decision.REJECTED


def test_snapshot_row_limit_fails_before_any_snapshot_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Row Limit")
    actor = _reviewer("row-limit", organization)
    for label in ("row-limit-one", "row-limit-two"):
        assertion = _career_assertion(organization=organization, actor=actor, label=label)
        _review(assertion, actor)
    monkeypatch.setattr(export_services, "MAX_EVIDENCE_ROWS", 1)
    audit_count = AuditEvent.objects.count()
    idempotency_count = IdempotencyRecord.objects.count()

    with pytest.raises(ValidationError, match="at most 1 rows"):
        _snapshot(actor, organization)

    assert EvidenceSnapshotManifest.objects.count() == 0
    assert IdempotencyRecord.objects.count() == idempotency_count
    assert AuditEvent.objects.count() == audit_count


def test_snapshot_canonical_size_limit_fails_before_any_snapshot_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Byte Limit")
    actor = _reviewer("byte-limit", organization)
    assertion = _career_assertion(organization=organization, actor=actor, label="byte-limit")
    _review(assertion, actor)
    monkeypatch.setattr(export_services, "MAX_EVIDENCE_SOURCE_BYTES", 64)
    audit_count = AuditEvent.objects.count()
    idempotency_count = IdempotencyRecord.objects.count()

    with pytest.raises(ValidationError, match="canonical source envelope exceeds 64 bytes"):
        _snapshot(actor, organization)

    assert EvidenceSnapshotManifest.objects.count() == 0
    assert IdempotencyRecord.objects.count() == idempotency_count
    assert AuditEvent.objects.count() == audit_count


@pytest.mark.parametrize(
    "score",
    [
        "2.999999999999999999999999999999999999999999999999999999",
        "180.000000000000000000000000000000000000000000000000000001",
    ],
)
def test_export_score_bounds_are_checked_exactly_before_float_conversion(score: str) -> None:
    organization = PartnerOrganization.objects.create(name=f"Synthetic Exact Score {score[:5]}")
    actor = _reviewer(f"exact-score-{hashlib.sha256(score.encode()).hexdigest()[:8]}", organization)
    assertion = _career_assertion(
        organization=organization,
        actor=actor,
        label=f"exact-score-{hashlib.sha256(score.encode()).hexdigest()[:8]}",
        score=score,
    )

    with pytest.raises(ValidationError, match="between 3 and 180"):
        _review(assertion, actor)


def test_snapshot_exports_only_latest_contiguous_source_revision() -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Corrected Source Snapshot")
    actor = _reviewer("corrected-source", organization)
    person = Person.objects.create()
    first = _career_assertion(
        organization=organization,
        actor=actor,
        label="corrected-source-v1",
        person=person,
        source_result_id="result-corrected-source",
        score="12.34",
    )
    _review(first, actor)
    second = _career_assertion(
        organization=organization,
        actor=actor,
        label="corrected-source-v2",
        person=person,
        source_result_id="result-corrected-source",
        source_revision=2,
        source_predecessor=first.source_result,
        score="11.11",
    )
    _review(second, actor)

    outcome = _snapshot(actor, organization)

    assert len(outcome.snapshot.rows) == 1
    assert outcome.snapshot.rows[0]["time_seconds"] == 11.11
    assert {
        item["reason"]
        for item in outcome.snapshot.exclusions
        if item["assertion_revision_id"] == str(first.pk)
    } == {"superseded_source_revision"}


def test_review_queue_candidates_exclude_superseded_source_revisions() -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Corrected Source Queue")
    actor = _reviewer("corrected-source-queue", organization)
    person = Person.objects.create()
    first = _career_assertion(
        organization=organization,
        actor=actor,
        label="corrected-source-queue-v1",
        person=person,
        source_result_id="result-corrected-source-queue",
    )
    second = _career_assertion(
        organization=organization,
        actor=actor,
        label="corrected-source-queue-v2",
        person=person,
        source_result_id="result-corrected-source-queue",
        source_revision=2,
        source_predecessor=first.source_result,
    )

    candidates = list(_current_assertions(PartnerOrganization.objects.filter(pk=organization.pk)))

    assert [candidate.pk for candidate in candidates] == [second.pk]


def test_historical_snapshot_ignores_assertions_and_source_corrections_created_later() -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Historical Source Snapshot")
    actor = _reviewer("historical-source", organization)
    person = Person.objects.create()
    first = _career_assertion(
        organization=organization,
        actor=actor,
        label="historical-source-v1",
        person=person,
        source_result_id="result-historical-source",
        score="12.34",
    )
    _review(first, actor)
    with mock.patch("django.utils.timezone.now", return_value=CAPTURED_AT + timedelta(minutes=1)):
        _career_assertion_unfrozen(
            organization=organization,
            actor=actor,
            label="historical-source-v2",
            person=person,
            source_result_id="result-historical-source",
            source_revision=2,
            source_predecessor=first.source_result,
            score="11.11",
        )

    outcome = _snapshot(actor, organization)

    assert [row["time_seconds"] for row in outcome.snapshot.rows] == [12.34]
    assert not any(
        exclusion["assertion_revision_id"] == str(first.pk)
        for exclusion in outcome.snapshot.exclusions
    )


def test_historical_snapshot_uses_identity_and_eligibility_state_as_of_capture() -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Historical Review Snapshot")
    actor = _reviewer("historical-review", organization)
    first_person = Person.objects.create()
    first = _career_assertion(
        organization=organization,
        actor=actor,
        label="historical-review",
        person=first_person,
    )
    _review(first, actor, decision=ExportEligibilityRevision.Decision.ELIGIBLE)
    with mock.patch("django.utils.timezone.now", return_value=CAPTURED_AT + timedelta(minutes=1)):
        review_export_eligibility(
            actor=actor,
            organization=organization,
            career_assertion=first,
            decision=ExportEligibilityRevision.Decision.REJECTED,
            reason="Future export correction",
            operator_key="future-export-correction",
        )
        CareerAssertionRevision.objects.create(
            organization=organization,
            source_result=first.source_result,
            person=Person.objects.create(),
            reconciliation_case=first.reconciliation_case,
            revision=2,
            predecessor=first,
            decision=CareerAssertionRevision.Decision.RELINK,
            authorization_basis_type=first.authorization_basis_type,
            authorization_basis_reference=first.authorization_basis_reference,
            authorization_captured_at=CAPTURED_AT + timedelta(minutes=1),
            reviewed_by=actor,
            source_payload_digest=first.source_payload_digest,
            decision_digest=_digest("future-identity-correction"),
        )

    outcome = _snapshot(actor, organization)

    assert len(outcome.snapshot.rows) == 1
    assert outcome.snapshot.exclusions == []


def test_historical_snapshot_treats_post_capture_eligibility_as_unreviewed() -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Future Eligibility")
    actor = _reviewer("future-eligibility", organization)
    assertion = _career_assertion(
        organization=organization,
        actor=actor,
        label="future-eligibility",
    )
    with mock.patch("django.utils.timezone.now", return_value=CAPTURED_AT + timedelta(minutes=1)):
        review_export_eligibility(
            actor=actor,
            organization=organization,
            career_assertion=assertion,
            decision=ExportEligibilityRevision.Decision.ELIGIBLE,
            reason="Reviewed after the historical capture",
            operator_key="future-eligibility-review",
        )

    outcome = _snapshot(actor, organization)

    assert outcome.snapshot.rows == []
    assert [item["reason"] for item in outcome.snapshot.exclusions] == ["unreviewed"]


def test_snapshot_candidate_limit_includes_excluded_assertions_before_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Candidate Limit")
    actor = _reviewer("candidate-limit", organization)
    for label in ("candidate-one", "candidate-two"):
        _career_assertion(organization=organization, actor=actor, label=label)
    monkeypatch.setattr(export_services, "MAX_SNAPSHOT_CANDIDATES", 1)
    audit_count = AuditEvent.objects.count()
    idempotency_count = IdempotencyRecord.objects.count()

    with pytest.raises(ValidationError, match="at most 1 candidate assertions"):
        _snapshot(actor, organization)

    assert EvidenceSnapshotManifest.objects.count() == 0
    assert IdempotencyRecord.objects.count() == idempotency_count
    assert AuditEvent.objects.count() == audit_count


def test_snapshot_full_manifest_size_includes_exclusions_before_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Manifest Byte Limit")
    actor = _reviewer("manifest-byte-limit", organization)
    _career_assertion(organization=organization, actor=actor, label="excluded-byte-limit")
    monkeypatch.setattr(export_services, "MAX_SNAPSHOT_MANIFEST_BYTES", 64)
    audit_count = AuditEvent.objects.count()
    idempotency_count = IdempotencyRecord.objects.count()

    with pytest.raises(ValidationError, match="full manifest exceeds 64 bytes"):
        _snapshot(actor, organization)

    assert EvidenceSnapshotManifest.objects.count() == 0
    assert IdempotencyRecord.objects.count() == idempotency_count
    assert AuditEvent.objects.count() == audit_count


def test_snapshot_replay_conflict_lineage_and_immutability() -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Snapshot History")
    actor = _reviewer("snapshot-history", organization)
    first_assertion = _career_assertion(
        organization=organization, actor=actor, label="snapshot-first"
    )
    _review(first_assertion, actor)

    first = _snapshot(actor, organization)
    replay = _snapshot(actor, organization)
    assert replay.replayed is True
    assert replay.snapshot.pk == first.snapshot.pk

    second_assertion = _career_assertion(
        organization=organization, actor=actor, label="snapshot-second"
    )
    _review(second_assertion, actor)
    with pytest.raises(IdempotencyConflict):
        _snapshot(actor, organization)
    with pytest.raises(IdempotencyConflict):
        _snapshot(
            actor,
            organization,
            source_id="mnemex:snapshot:synthetic-2026-08-02",
            key="different-operator-key",
        )

    second = _snapshot(
        actor,
        organization,
        source_id="mnemex:snapshot:synthetic-2026-08-03",
        key="snapshot-synthetic-2026-08-03",
    )
    assert second.snapshot.predecessor_id == first.snapshot.pk
    with pytest.raises(PermissionDenied, match="immutable"):
        EvidenceSnapshotManifest.objects.filter(pk=first.snapshot.pk).delete()


@pytest.mark.strathmark_contract
def test_stored_snapshot_source_round_trips_through_strathmark_2_result_store(tmp_path) -> None:
    strathmark = pytest.importorskip("strathmark")
    assert int(strathmark.__version__.split(".")[0]) == 2
    from strathmark.store import ResultStore, canonical_evidence_source_digest

    organization = PartnerOrganization.objects.create(name="Synthetic E2E Contract")
    actor = _reviewer("e2e", organization)
    assertion = _career_assertion(organization=organization, actor=actor, label="e2e")
    _review(assertion, actor)
    snapshot = _snapshot(actor, organization).snapshot
    source = StoredEvidenceSnapshotSource(snapshot)

    assert snapshot.source_digest == canonical_evidence_source_digest(
        source_id=snapshot.source_id,
        cutoff=snapshot.cutoff,
        captured_at=snapshot.captured_at,
        rows=snapshot.rows,
    )
    store = ResultStore(tmp_path / "strathmark-evidence-contract.db")
    status = store.refresh_evidence_snapshot(source, cutoff=CUTOFF)

    assert status.source_digest == snapshot.source_digest
    assert status.accepted_row_count == 1
    competitor_id = snapshot.rows[0]["competitor_id"]
    history = store.get_evidence_history(competitor_id, "UH")
    assert len(history) == 1
    assert history[0].time_seconds == 12.34
    assert history[0].species == "white_pine"
    assert history[0].diameter_mm == 325
