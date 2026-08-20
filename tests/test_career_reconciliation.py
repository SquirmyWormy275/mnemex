from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from mnemex.accounts.models import Account, PrivilegedRoleAssignment
from mnemex.career.models import CareerAssertionRevision
from mnemex.career.services import CAREER_IDENTITY_RECONCILIATION_PURPOSE, reconcile_identity
from mnemex.consent.models import ConsentGrant
from mnemex.foundation.models import AuditEvent
from mnemex.foundation.services import IdempotencyConflict
from mnemex.partners.models import PartnerClient, PartnerOrganization
from mnemex.people.models import Alias, GuardianRelationship, Person
from mnemex.results.models import (
    IngestionRun,
    MappingTemplate,
    PublishedSourceResult,
    ReconciliationCase,
    SourceArtifact,
    StagedResult,
)
from mnemex.results.services import ingest_manual_rows
from tests.mfa_helpers import enroll_account_mfa

pytestmark = pytest.mark.django_db


def _reviewer(label: str, *, identity_reviewer: bool = True, mfa_enrolled: bool = True) -> Account:
    account = Account.objects.create_user(email=f"{label}@mnemex.example.invalid", password=None)
    if mfa_enrolled:
        enroll_account_mfa(account)
    if identity_reviewer:
        PrivilegedRoleAssignment.objects.create(
            account=account,
            role=PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER,
            assigned_by=account,
        )
    return account


def test_ingestion_never_auto_links_an_existing_matching_alias() -> None:
    actor = _reviewer("no-auto-link")
    PrivilegedRoleAssignment.objects.create(
        account=actor,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        assigned_by=actor,
    )
    organization = PartnerOrganization.objects.create(name="Synthetic No Auto-link Show")
    person = Person.objects.create()
    Alias.objects.create(
        person=person,
        value="Synthetic Competitor",
        normalized_value="synthetic competitor",
        source="synthetic-test",
        review_state=Alias.ReviewState.APPROVED,
    )
    mapping = MappingTemplate.objects.create(
        organization=organization,
        name="synthetic career mapping",
        version=1,
        field_map={
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
        },
        created_by=actor,
    )

    outcome = ingest_manual_rows(
        actor=actor,
        organization=organization,
        mapping_template=mapping,
        operator_key="no-auto-link",
        rows=[
            {
                "result_id": "result-no-auto-link",
                "revision": 1,
                "event_id": "synthetic-show-2026",
                "event_name": "Synthetic Summer Show",
                "result_date": "2026-07-18",
                "competitor": "Synthetic Competitor",
                "event": "UNDERHAND",
                "score_kind": "time",
                "result": "12.34",
                "heat_id": "heat-1",
                "wood_species": "white pine",
                "wood_diameter_mm": "325",
                "wood_quality": "8",
            }
        ],
    )

    published = PublishedSourceResult.objects.get(staged_result__run=outcome.run)
    assert published.person_id is None
    assert CareerAssertionRevision.objects.count() == 0
    assert ReconciliationCase.objects.filter(
        existing_published_result=published,
        case_type=ReconciliationCase.CaseType.IDENTITY_UNRESOLVED,
        status=ReconciliationCase.Status.OPEN,
    ).exists()


def _identity_case(
    *,
    organization: PartnerOrganization,
    actor: Account,
    label: str,
    include_source_event: bool = True,
) -> tuple[PublishedSourceResult, ReconciliationCase]:
    digest = (label.encode("utf-8").hex() + ("0" * 64))[:64]
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
    source_payload = {
        "source_result_id": f"result-{label}",
        "competitor_name": "Synthetic Competitor",
        "discipline": "UNDERHAND",
        "score_type": "time",
        "score": "12.34",
    }
    if include_source_event:
        source_payload["source_event_id"] = f"event-{label}"
    staged = StagedResult.objects.create(
        run=run,
        row_number=1,
        source_result_id=f"result-{label}",
        source_revision=1,
        normalized_payload=source_payload,
        payload_digest=digest,
        validation_errors=[],
        outcome=StagedResult.Outcome.PUBLISHED,
        proposed_person_ids=[],
    )
    published = PublishedSourceResult.objects.create(
        organization=organization,
        source_result_id=f"result-{label}",
        source_revision=1,
        discipline="UNDERHAND",
        score_type="time",
        normalized_payload=source_payload,
        payload_digest=digest,
        artifact=artifact,
        staged_result=staged,
        person=None,
    )
    case = ReconciliationCase.objects.create(
        case_type=ReconciliationCase.CaseType.IDENTITY_UNRESOLVED,
        staged_result=staged,
        existing_published_result=published,
        details={"reason": "source identity requires explicit reconciliation"},
    )
    run.status = IngestionRun.Status.COMPLETED
    run.total_rows = 1
    run.published_rows = 1
    run.completed_at = timezone.now()
    run.save()
    return published, case


def _consent_client(
    organization: PartnerOrganization, *, name: str = "Synthetic career reconciliation"
) -> PartnerClient:
    return PartnerClient.objects.create(
        organization=organization,
        name=name,
        environment=PartnerClient.Environment.SANDBOX,
        allowed_purposes=[CAREER_IDENTITY_RECONCILIATION_PURPOSE],
        allowed_field_groups=[ConsentGrant.FieldGroup.CAREER_SUMMARY],
    )


def _consent_grant(
    *,
    person: Person,
    acting_account: Account,
    client: PartnerClient,
    context_id: str,
    guardian_relationship: GuardianRelationship | None = None,
) -> ConsentGrant:
    return ConsentGrant.objects.create(
        person=person,
        acting_account=acting_account,
        guardian_relationship=guardian_relationship,
        recipient_client=client,
        purpose=CAREER_IDENTITY_RECONCILIATION_PURPOSE,
        field_groups=[ConsentGrant.FieldGroup.CAREER_SUMMARY],
        context_id=context_id,
        expires_at=timezone.now() + timedelta(days=1),
        policy_version="synthetic-career-consent-v1",
    )


def _consent_reconcile(
    *,
    actor: Account,
    organization: PartnerOrganization,
    case: ReconciliationCase,
    person: Person,
    basis: CareerAssertionRevision.AuthorizationBasis,
    grant: ConsentGrant | None,
    operator_key: str,
):
    return reconcile_identity(
        actor=actor,
        organization=organization,
        reconciliation_case=case,
        person=person,
        authorization_basis_type=basis,
        authorization_basis_reference="fabricated free text must not authorize",
        authorization_captured_at=timezone.now(),
        operator_key=operator_key,
        consent_grant=grant,
    )


def _reconcile(
    *,
    actor: Account,
    organization: PartnerOrganization,
    case: ReconciliationCase,
    person: Person,
    operator_key: str,
):
    return reconcile_identity(
        actor=actor,
        organization=organization,
        reconciliation_case=case,
        person=person,
        authorization_basis_type=CareerAssertionRevision.AuthorizationBasis.SOURCE_DATA_RIGHTS,
        authorization_basis_reference="synthetic-policy:results-rights:v1",
        authorization_captured_at=timezone.now(),
        operator_key=operator_key,
    )


@pytest.mark.parametrize(
    ("identity_reviewer", "mfa_enrolled"),
    [(False, True), (True, False)],
)
def test_identity_reconciliation_requires_mfa_bound_identity_reviewer(
    identity_reviewer: bool, mfa_enrolled: bool
) -> None:
    actor = _reviewer(
        f"denied-{identity_reviewer}-{mfa_enrolled}",
        identity_reviewer=identity_reviewer,
        mfa_enrolled=mfa_enrolled,
    )
    organization = PartnerOrganization.objects.create(
        name=f"Synthetic Denied {identity_reviewer} {mfa_enrolled}"
    )
    published, case = _identity_case(
        organization=organization, actor=actor, label=str(uuid.uuid4())
    )

    with pytest.raises(PermissionDenied, match="identity reviewer"):
        _reconcile(
            actor=actor,
            organization=organization,
            case=case,
            person=Person.objects.create(),
            operator_key="denied",
        )

    assert published.person_id is None
    assert CareerAssertionRevision.objects.count() == 0


def test_approval_is_explicit_idempotent_and_auditable_without_mutating_source() -> None:
    actor = _reviewer("approve")
    organization = PartnerOrganization.objects.create(name="Synthetic Approval Show")
    published, case = _identity_case(organization=organization, actor=actor, label="approval")
    person = Person.objects.create()
    source_payload_before = dict(published.normalized_payload)
    captured_at = timezone.now()
    kwargs = {
        "actor": actor,
        "organization": organization,
        "reconciliation_case": case,
        "person": person,
        "authorization_basis_type": CareerAssertionRevision.AuthorizationBasis.SOURCE_DATA_RIGHTS,
        "authorization_basis_reference": "synthetic-policy:results-rights:v1",
        "authorization_captured_at": captured_at,
        "operator_key": "approve-identity-1",
    }

    first = reconcile_identity(**kwargs)
    replay = reconcile_identity(**kwargs)

    assertion = first.assertion
    assert first.replayed is False
    assert replay.replayed is True
    assert replay.assertion.pk == assertion.pk
    assert assertion.source_result_id == published.pk
    assert assertion.person_id == person.pk
    assert assertion.revision == 1
    assert assertion.predecessor_id is None
    assert assertion.decision == CareerAssertionRevision.Decision.APPROVE_LINK
    assert assertion.authorization_basis_reference == "synthetic-policy:results-rights:v1"
    assert assertion.authorization_captured_at == captured_at
    assert assertion.reviewed_by_id == actor.pk
    assert assertion.source_payload_digest == published.payload_digest
    assert assertion.is_current is True
    case.refresh_from_db()
    published.refresh_from_db()
    assert case.status == ReconciliationCase.Status.RESOLVED
    assert case.resolved_by_id == actor.pk
    assert published.person_id is None
    assert published.normalized_payload == source_payload_before
    assert CareerAssertionRevision.objects.count() == 1

    event = AuditEvent.objects.get(action="career.identity_link_approved")
    assert event.actor_id == actor.pk
    assert event.target_type == "career_assertion_revision"
    assert event.target_id == str(assertion.pk)
    assert event.payload_digest == assertion.decision_digest
    assert event.metadata == {
        "authorization_basis_type": "source_data_rights",
        "case_id": str(case.pk),
        "organization_id": str(organization.pk),
        "person_id": str(person.pk),
        "revision": 1,
        "source_result_id": str(published.pk),
    }
    assert "competitor_name" not in str(event.metadata)


def test_changed_decision_cannot_reuse_idempotency_key() -> None:
    actor = _reviewer("conflict")
    organization = PartnerOrganization.objects.create(name="Synthetic Conflict Review Show")
    _, case = _identity_case(organization=organization, actor=actor, label="review-conflict")
    first_person = Person.objects.create()
    second_person = Person.objects.create()

    _reconcile(
        actor=actor,
        organization=organization,
        case=case,
        person=first_person,
        operator_key="same-review-key",
    )

    with pytest.raises(IdempotencyConflict):
        _reconcile(
            actor=actor,
            organization=organization,
            case=case,
            person=second_person,
            operator_key="same-review-key",
        )

    assert CareerAssertionRevision.objects.count() == 1


def test_relink_appends_successor_and_preserves_prior_revision_and_source() -> None:
    actor = _reviewer("relink")
    organization = PartnerOrganization.objects.create(name="Synthetic Relink Show")
    published, case = _identity_case(organization=organization, actor=actor, label="relink")
    first_person = Person.objects.create()
    corrected_person = Person.objects.create()
    source_payload_before = dict(published.normalized_payload)
    first = _reconcile(
        actor=actor,
        organization=organization,
        case=case,
        person=first_person,
        operator_key="initial-link",
    ).assertion

    corrected = _reconcile(
        actor=actor,
        organization=organization,
        case=case,
        person=corrected_person,
        operator_key="corrected-link",
    ).assertion

    first.refresh_from_db()
    published.refresh_from_db()
    assert corrected.revision == 2
    assert corrected.predecessor_id == first.pk
    assert corrected.decision == CareerAssertionRevision.Decision.RELINK
    assert corrected.person_id == corrected_person.pk
    assert corrected.is_current is True
    assert first.revision == 1
    assert first.person_id == first_person.pk
    assert first.is_current is False
    assert published.person_id is None
    assert published.normalized_payload == source_payload_before
    assert list(
        CareerAssertionRevision.objects.filter(source_result=published)
        .order_by("revision")
        .values_list("revision", flat=True)
    ) == [1, 2]
    correction_event = AuditEvent.objects.get(action="career.identity_link_corrected")
    assert correction_event.metadata["predecessor_assertion_id"] == str(first.pk)


def test_assertions_are_immutable() -> None:
    actor = _reviewer("immutable")
    organization = PartnerOrganization.objects.create(name="Synthetic Immutable Career Show")
    _, case = _identity_case(organization=organization, actor=actor, label="immutable")
    assertion = _reconcile(
        actor=actor,
        organization=organization,
        case=case,
        person=Person.objects.create(),
        operator_key="immutable-link",
    ).assertion
    assertion.authorization_basis_reference = "changed"

    with pytest.raises(PermissionDenied, match="immutable"):
        assertion.save()
    with pytest.raises(PermissionDenied, match="immutable"):
        CareerAssertionRevision.objects.filter(pk=assertion.pk).delete()


def test_case_must_be_reviewed_in_its_source_organization_scope() -> None:
    actor = _reviewer("wrong-organization")
    source_organization = PartnerOrganization.objects.create(name="Synthetic Source Show")
    wrong_organization = PartnerOrganization.objects.create(name="Synthetic Wrong Show")
    published, case = _identity_case(
        organization=source_organization, actor=actor, label="wrong-organization"
    )

    with pytest.raises(PermissionDenied, match="organization scope"):
        _reconcile(
            actor=actor,
            organization=wrong_organization,
            case=case,
            person=Person.objects.create(),
            operator_key="wrong-organization",
        )

    assert published.person_id is None
    assert CareerAssertionRevision.objects.count() == 0


def test_identity_reviewer_role_cannot_cross_organization_tenants() -> None:
    actor = _reviewer("tenant-bounded-reviewer", identity_reviewer=False)
    organization_a = PartnerOrganization.objects.create(name="Synthetic Reviewer Show A")
    organization_b = PartnerOrganization.objects.create(name="Synthetic Reviewer Show B")
    PrivilegedRoleAssignment.objects.create(
        account=actor,
        role=PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER,
        assigned_by=actor,
        scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
        organization=organization_a,
    )
    published, case = _identity_case(
        organization=organization_b, actor=actor, label="cross-tenant-role"
    )

    with pytest.raises(PermissionDenied, match="identity reviewer"):
        _reconcile(
            actor=actor,
            organization=organization_b,
            case=case,
            person=Person.objects.create(),
            operator_key="cross-tenant-role",
        )

    assert published.person_id is None
    assert CareerAssertionRevision.objects.count() == 0


def test_non_identity_case_and_inactive_person_are_rejected() -> None:
    actor = _reviewer("invalid-state")
    organization = PartnerOrganization.objects.create(name="Synthetic Invalid State Show")
    _, case = _identity_case(organization=organization, actor=actor, label="invalid-state")
    case.case_type = ReconciliationCase.CaseType.SOURCE_PAYLOAD_CONFLICT
    case.save(update_fields=["case_type"])

    with pytest.raises(ValidationError, match="identity-unresolved"):
        _reconcile(
            actor=actor,
            organization=organization,
            case=case,
            person=Person.objects.create(),
            operator_key="wrong-case-type",
        )

    case.case_type = ReconciliationCase.CaseType.IDENTITY_UNRESOLVED
    case.save(update_fields=["case_type"])
    inactive_person = Person.objects.create(status=Person.Status.REDACTED)
    with pytest.raises(ValidationError, match="active person"):
        _reconcile(
            actor=actor,
            organization=organization,
            case=case,
            person=inactive_person,
            operator_key="inactive-person",
        )


def test_free_text_cannot_fabricate_competitor_or_guardian_consent() -> None:
    actor = _reviewer("fabricated-consent")
    organization = PartnerOrganization.objects.create(name="Synthetic Fabricated Consent Show")
    _, case = _identity_case(organization=organization, actor=actor, label="fabricated-consent")
    person = Person.objects.create(age_classification=Person.AgeClassification.ADULT)

    for basis in (
        CareerAssertionRevision.AuthorizationBasis.COMPETITOR_CONSENT,
        CareerAssertionRevision.AuthorizationBasis.GUARDIAN_CONSENT,
    ):
        with pytest.raises(ValidationError, match="consent grant"):
            _consent_reconcile(
                actor=actor,
                organization=organization,
                case=case,
                person=person,
                basis=basis,
                grant=None,
                operator_key=f"fabricated-{basis}",
            )

    assert CareerAssertionRevision.objects.count() == 0


def test_valid_adult_competitor_consent_is_typed_and_auditable() -> None:
    actor = _reviewer("adult-consent-reviewer")
    organization = PartnerOrganization.objects.create(name="Synthetic Adult Consent Show")
    _, case = _identity_case(organization=organization, actor=actor, label="adult-consent")
    subject = Account.objects.create_user(
        email="adult-subject@mnemex.example.invalid", password=None
    )
    person = Person.objects.create(
        account=subject,
        age_classification=Person.AgeClassification.ADULT,
    )
    grant = _consent_grant(
        person=person,
        acting_account=subject,
        client=_consent_client(organization),
        context_id="event-adult-consent",
    )

    assertion = _consent_reconcile(
        actor=actor,
        organization=organization,
        case=case,
        person=person,
        basis=CareerAssertionRevision.AuthorizationBasis.COMPETITOR_CONSENT,
        grant=grant,
        operator_key="adult-consent-link",
    ).assertion

    assert assertion.consent_grant_id == grant.pk
    assert assertion.authorization_basis_reference == str(grant.pk)
    assert assertion.decision_digest


@pytest.mark.parametrize(
    "invalidity",
    [
        "wrong_tenant",
        "wrong_person",
        "wrong_purpose",
        "wrong_context",
        "missing_career_summary",
        "expired",
        "revoked",
        "issued_after_capture",
        "wrong_subject_account",
        "inactive_client",
        "has_guardian",
    ],
)
def test_competitor_consent_fails_closed_for_invalid_grant(invalidity: str) -> None:
    actor = _reviewer(f"invalid-consent-{invalidity}")
    organization = PartnerOrganization.objects.create(name=f"Synthetic Invalid {invalidity}")
    _, case = _identity_case(
        organization=organization,
        actor=actor,
        label=f"invalid-consent-{invalidity}",
    )
    subject = Account.objects.create_user(
        email=f"subject-{invalidity}@mnemex.example.invalid", password=None
    )
    person = Person.objects.create(
        account=subject,
        age_classification=Person.AgeClassification.ADULT,
    )
    client = _consent_client(organization)
    grant_person = person
    grant_actor = subject
    grant_relationship = None
    if invalidity == "wrong_tenant":
        other = PartnerOrganization.objects.create(name=f"Synthetic Other {invalidity}")
        client = _consent_client(other, name=f"Other {invalidity}")
    elif invalidity == "wrong_person":
        other_subject = Account.objects.create_user(
            email=f"other-{invalidity}@mnemex.example.invalid", password=None
        )
        grant_person = Person.objects.create(
            account=other_subject,
            age_classification=Person.AgeClassification.ADULT,
        )
        grant_actor = other_subject
    elif invalidity == "wrong_subject_account":
        grant_actor = Account.objects.create_user(
            email=f"wrong-authority-{invalidity}@mnemex.example.invalid", password=None
        )
    elif invalidity == "inactive_client":
        client.status = PartnerClient.Status.SUSPENDED
        client.save(update_fields=["status"])
    elif invalidity == "has_guardian":
        now = timezone.now()
        grant_relationship = GuardianRelationship.objects.create(
            guardian_account=subject,
            minor_person=person,
            authority_basis="synthetic inapplicable guardian authority",
            verification_state=GuardianRelationship.VerificationState.VERIFIED,
            jurisdiction="MT",
            policy_version="synthetic-minor-policy-v1",
            effective_at=now - timedelta(days=1),
            verified_at=now - timedelta(days=1),
        )
    grant = _consent_grant(
        person=grant_person,
        acting_account=grant_actor,
        client=client,
        context_id=f"event-invalid-consent-{invalidity}",
        guardian_relationship=grant_relationship,
    )
    updates: dict[str, object] = {}
    if invalidity == "wrong_purpose":
        updates["purpose"] = "registration"
    elif invalidity == "wrong_context":
        updates["context_id"] = "different-event"
    elif invalidity == "missing_career_summary":
        updates["field_groups"] = [ConsentGrant.FieldGroup.BASIC_IDENTITY]
    elif invalidity == "expired":
        updates["expires_at"] = timezone.now() - timedelta(seconds=1)
    elif invalidity == "revoked":
        updates["revoked_at"] = timezone.now()
    elif invalidity == "issued_after_capture":
        updates["issued_at"] = timezone.now() + timedelta(hours=1)
    if updates:
        ConsentGrant.objects.filter(pk=grant.pk).update(**updates)
        grant.refresh_from_db()

    with pytest.raises((PermissionDenied, ValidationError)):
        _consent_reconcile(
            actor=actor,
            organization=organization,
            case=case,
            person=person,
            basis=CareerAssertionRevision.AuthorizationBasis.COMPETITOR_CONSENT,
            grant=grant,
            operator_key=f"invalid-{invalidity}",
        )

    assert CareerAssertionRevision.objects.count() == 0


def test_consent_basis_fails_closed_when_source_event_context_is_absent() -> None:
    actor = _reviewer("missing-event-consent")
    organization = PartnerOrganization.objects.create(name="Synthetic Missing Event Consent")
    _, case = _identity_case(
        organization=organization,
        actor=actor,
        label="missing-event-consent",
        include_source_event=False,
    )
    subject = Account.objects.create_user(
        email="missing-event-subject@mnemex.example.invalid", password=None
    )
    person = Person.objects.create(
        account=subject,
        age_classification=Person.AgeClassification.ADULT,
    )
    grant = _consent_grant(
        person=person,
        acting_account=subject,
        client=_consent_client(organization),
        context_id="event-missing-event-consent",
    )

    with pytest.raises(ValidationError, match="event context"):
        _consent_reconcile(
            actor=actor,
            organization=organization,
            case=case,
            person=person,
            basis=CareerAssertionRevision.AuthorizationBasis.COMPETITOR_CONSENT,
            grant=grant,
            operator_key="missing-event-context",
        )


def test_valid_guardian_consent_requires_current_verified_minor_authority() -> None:
    actor = _reviewer("guardian-consent-reviewer")
    organization = PartnerOrganization.objects.create(name="Synthetic Guardian Consent Show")
    _, case = _identity_case(organization=organization, actor=actor, label="guardian-consent")
    guardian = Account.objects.create_user(
        email="verified-guardian@mnemex.example.invalid", password=None
    )
    minor = Person.objects.create(age_classification=Person.AgeClassification.MINOR)
    now = timezone.now()
    relationship = GuardianRelationship.objects.create(
        guardian_account=guardian,
        minor_person=minor,
        authority_basis="synthetic verified guardian",
        verification_state=GuardianRelationship.VerificationState.VERIFIED,
        jurisdiction="MT",
        policy_version="synthetic-minor-policy-v1",
        effective_at=now - timedelta(days=1),
        verified_at=now - timedelta(days=1),
    )
    grant = _consent_grant(
        person=minor,
        acting_account=guardian,
        client=_consent_client(organization),
        context_id="event-guardian-consent",
        guardian_relationship=relationship,
    )

    assertion = _consent_reconcile(
        actor=actor,
        organization=organization,
        case=case,
        person=minor,
        basis=CareerAssertionRevision.AuthorizationBasis.GUARDIAN_CONSENT,
        grant=grant,
        operator_key="guardian-consent-link",
    ).assertion
    assert assertion.consent_grant_id == grant.pk


@pytest.mark.parametrize("invalidity", ["adult", "pending", "expired", "wrong_guardian"])
def test_guardian_consent_rejects_invalid_guardian_authority(invalidity: str) -> None:
    actor = _reviewer(f"guardian-invalid-{invalidity}")
    organization = PartnerOrganization.objects.create(name=f"Synthetic Guardian {invalidity}")
    _, case = _identity_case(
        organization=organization,
        actor=actor,
        label=f"guardian-invalid-{invalidity}",
    )
    guardian = Account.objects.create_user(
        email=f"guardian-{invalidity}@mnemex.example.invalid", password=None
    )
    person = Person.objects.create(
        age_classification=(
            Person.AgeClassification.ADULT
            if invalidity == "adult"
            else Person.AgeClassification.MINOR
        )
    )
    now = timezone.now()
    relationship = GuardianRelationship.objects.create(
        guardian_account=guardian,
        minor_person=person,
        authority_basis="synthetic guardian authority",
        verification_state=(
            GuardianRelationship.VerificationState.PENDING
            if invalidity == "pending"
            else GuardianRelationship.VerificationState.VERIFIED
        ),
        jurisdiction="MT",
        policy_version="synthetic-minor-policy-v1",
        effective_at=now - timedelta(days=1),
        verified_at=None if invalidity == "pending" else now - timedelta(days=1),
        expires_at=now - timedelta(seconds=1) if invalidity == "expired" else None,
    )
    grant_actor = guardian
    if invalidity == "wrong_guardian":
        grant_actor = Account.objects.create_user(
            email="wrong-guardian@mnemex.example.invalid", password=None
        )
    grant = _consent_grant(
        person=person,
        acting_account=grant_actor,
        client=_consent_client(organization),
        context_id=f"event-guardian-invalid-{invalidity}",
        guardian_relationship=relationship,
    )

    with pytest.raises((PermissionDenied, ValidationError)):
        _consent_reconcile(
            actor=actor,
            organization=organization,
            case=case,
            person=person,
            basis=CareerAssertionRevision.AuthorizationBasis.GUARDIAN_CONSENT,
            grant=grant,
            operator_key=f"guardian-invalid-{invalidity}",
        )

    assert CareerAssertionRevision.objects.count() == 0
