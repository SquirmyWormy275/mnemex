from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from mnemex.accounts.authorization import Action, may_perform
from mnemex.accounts.models import Account
from mnemex.career.models import CareerAssertionRevision
from mnemex.consent.models import ConsentGrant
from mnemex.foundation.models import IdempotencyRecord
from mnemex.foundation.services import claim_idempotency, record_audit_event
from mnemex.partners.models import PartnerClient, PartnerOrganization
from mnemex.people.models import GuardianRelationship, Person
from mnemex.results.models import PublishedSourceResult, ReconciliationCase


@dataclass(frozen=True)
class CareerReconciliationOutcome:
    assertion: CareerAssertionRevision
    replayed: bool


CAREER_IDENTITY_RECONCILIATION_PURPOSE = "career.identity_reconciliation"
_CONSENT_BASES = {
    CareerAssertionRevision.AuthorizationBasis.COMPETITOR_CONSENT,
    CareerAssertionRevision.AuthorizationBasis.GUARDIAN_CONSENT,
}


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _authorize(actor: Account, organization: PartnerOrganization) -> None:
    if not may_perform(actor, Action.REVIEW_IDENTITY, organization=organization):
        raise PermissionDenied("an MFA-bound identity reviewer role is required")


def _validate_reference(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 240:
        raise ValidationError("authorization basis reference must contain 1 to 240 characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ValidationError("authorization basis reference cannot contain control characters")
    return normalized


def _validate_captured_at(value: datetime) -> datetime:
    if timezone.is_naive(value):
        raise ValidationError("authorization capture time must include a timezone")
    if value > timezone.now():
        raise ValidationError("authorization capture time cannot be in the future")
    return value


def _invalid_consent() -> ValidationError:
    return ValidationError("consent grant is not valid for this identity reconciliation")


def _validate_consent_grant(
    *,
    consent_grant: ConsentGrant | None,
    basis_type: str,
    person: Person,
    organization: PartnerOrganization,
    source_result: PublishedSourceResult,
    captured_at: datetime,
) -> ConsentGrant:
    if consent_grant is None:
        raise ValidationError("a consent grant is required for a consent authorization basis")
    # Lock nullable authority references separately. PostgreSQL rejects
    # ``FOR UPDATE`` on the nullable side of an outer join, and separate locks
    # also make the exact records whose state authorizes this decision explicit.
    grant = ConsentGrant.objects.select_for_update().filter(pk=consent_grant.pk).first()
    if grant is None:
        raise _invalid_consent()
    client = PartnerClient.objects.select_for_update().filter(pk=grant.recipient_client_id).first()
    acting_account = Account.objects.select_for_update().filter(pk=grant.acting_account_id).first()
    if client is None or acting_account is None:
        raise _invalid_consent()
    source_event_id = source_result.normalized_payload.get("source_event_id")
    if not isinstance(source_event_id, str) or not source_event_id.strip():
        raise ValidationError("source result has no event context for consent validation")
    now = timezone.now()
    common_valid = (
        grant.person_id == person.pk
        and client.organization_id == organization.pk
        and client.status == PartnerClient.Status.ACTIVE
        and client.revoked_at is None
        and grant.purpose == CAREER_IDENTITY_RECONCILIATION_PURPOSE
        and grant.purpose in client.allowed_purposes
        and grant.context_id == source_event_id
        and ConsentGrant.FieldGroup.CAREER_SUMMARY in grant.field_groups
        and ConsentGrant.FieldGroup.CAREER_SUMMARY in client.allowed_field_groups
        and grant.issued_at <= captured_at
        and grant.expires_at > captured_at
        and grant.expires_at > now
        and grant.revoked_at is None
        and acting_account.is_active
    )
    if not common_valid:
        raise _invalid_consent()
    if basis_type == CareerAssertionRevision.AuthorizationBasis.COMPETITOR_CONSENT:
        if (
            grant.guardian_relationship_id is not None
            or person.age_classification != Person.AgeClassification.ADULT
            or person.account_id is None
            or grant.acting_account_id != person.account_id
        ):
            raise _invalid_consent()
        return grant
    relationship_id = grant.guardian_relationship_id
    if relationship_id is None:
        raise _invalid_consent()
    relationship = (
        GuardianRelationship.objects.select_for_update().filter(pk=relationship_id).first()
    )
    if relationship is None:
        raise _invalid_consent()
    guardian_valid = (
        person.age_classification == Person.AgeClassification.MINOR
        and relationship.minor_person_id == person.pk
        and relationship.guardian_account_id == grant.acting_account_id
        and relationship.verification_state == relationship.VerificationState.VERIFIED
        and relationship.verified_at is not None
        and relationship.verified_at <= captured_at
        and relationship.effective_at <= captured_at
        and (relationship.expires_at is None or relationship.expires_at > captured_at)
        and (relationship.expires_at is None or relationship.expires_at > now)
        and relationship.revoked_at is None
        and relationship.is_active
    )
    if not guardian_valid:
        raise _invalid_consent()
    return grant


def _validate_authorization_evidence(
    *,
    basis_type: str,
    reference: str,
    consent_grant: ConsentGrant | None,
    person: Person,
    organization: PartnerOrganization,
    source_result: PublishedSourceResult,
    captured_at: datetime,
) -> tuple[str, ConsentGrant | None]:
    if basis_type in _CONSENT_BASES:
        grant = _validate_consent_grant(
            consent_grant=consent_grant,
            basis_type=basis_type,
            person=person,
            organization=organization,
            source_result=source_result,
            captured_at=captured_at,
        )
        return str(grant.pk), grant
    if consent_grant is not None:
        raise ValidationError("consent grant evidence is not valid for this authorization basis")
    return _validate_reference(reference), None


def _replayed_outcome(record: IdempotencyRecord) -> CareerReconciliationOutcome | None:
    response = record.response
    if record.status != IdempotencyRecord.Status.COMPLETED or not isinstance(response, dict):
        return None
    assertion_id = response.get("assertion_revision_id")
    if not isinstance(assertion_id, str):
        return None
    assertion = CareerAssertionRevision.objects.filter(pk=assertion_id).first()
    if assertion is None:
        return None
    return CareerReconciliationOutcome(assertion=assertion, replayed=True)


def _finish_idempotency(record: IdempotencyRecord, assertion: CareerAssertionRevision) -> None:
    record.status = IdempotencyRecord.Status.COMPLETED
    record.response = {"assertion_revision_id": str(assertion.pk)}
    record.save(update_fields=["status", "response", "updated_at"])


@transaction.atomic
def reconcile_identity(
    *,
    actor: Account,
    organization: PartnerOrganization,
    reconciliation_case: ReconciliationCase,
    person: Person,
    authorization_basis_type: CareerAssertionRevision.AuthorizationBasis | str,
    authorization_basis_reference: str,
    authorization_captured_at: datetime,
    operator_key: str,
    consent_grant: ConsentGrant | None = None,
) -> CareerReconciliationOutcome:
    """Approve or correct a source-result identity through an append-only decision."""

    _authorize(actor, organization)
    captured_at = _validate_captured_at(authorization_captured_at)
    basis_type = str(authorization_basis_type)
    if basis_type not in CareerAssertionRevision.AuthorizationBasis.values:
        raise ValidationError("authorization basis type is not recognized")
    normalized_key = operator_key.strip()
    if not normalized_key or len(normalized_key) > 200:
        raise ValidationError("operator key must contain 1 to 200 characters")

    current_organization = (
        PartnerOrganization.objects.select_for_update().filter(pk=organization.pk).first()
    )
    if (
        current_organization is None
        or current_organization.status != PartnerOrganization.Status.ACTIVE
    ):
        raise ValidationError("source organization is not active")
    current_case = (
        ReconciliationCase.objects.select_for_update().filter(pk=reconciliation_case.pk).first()
    )
    if current_case is None:
        raise ValidationError("reconciliation case does not exist")
    source_result_id = current_case.existing_published_result_id
    if source_result_id is None:
        raise ValidationError("identity case has no published source result")
    source_result = PublishedSourceResult.objects.select_for_update().get(pk=source_result_id)
    if source_result.organization_id != current_organization.pk:
        raise PermissionDenied("identity case is outside the requested organization scope")

    current_person = Person.objects.select_for_update().filter(pk=person.pk).first()
    if current_person is None or current_person.status != Person.Status.ACTIVE:
        raise ValidationError("identity reconciliation requires an active person")

    reference, current_grant = _validate_authorization_evidence(
        basis_type=basis_type,
        reference=authorization_basis_reference,
        consent_grant=consent_grant,
        person=current_person,
        organization=current_organization,
        source_result=source_result,
        captured_at=captured_at,
    )

    request_digest = _canonical_digest(
        {
            "actor_id": str(actor.pk),
            "authorization_basis_reference": reference,
            "authorization_basis_type": basis_type,
            "authorization_captured_at": captured_at.isoformat(),
            "consent_grant_id": str(current_grant.pk) if current_grant is not None else None,
            "case_id": str(current_case.pk),
            "organization_id": str(current_organization.pk),
            "person_id": str(current_person.pk),
            "source_payload_digest": source_result.payload_digest,
            "source_result_id": str(source_result.pk),
        }
    )
    record, _ = claim_idempotency(
        scope=f"career-identity-reconciliation:{current_organization.pk}",
        key=normalized_key,
        request_digest=request_digest,
    )
    replay = _replayed_outcome(record)
    if replay is not None:
        return replay

    if current_case.case_type != ReconciliationCase.CaseType.IDENTITY_UNRESOLVED:
        raise ValidationError("only an identity-unresolved case can be reconciled")
    if current_case.status == ReconciliationCase.Status.REJECTED:
        raise ValidationError("a rejected identity case cannot be reconciled")
    if current_case.staged_result_id != source_result.staged_result_id:
        raise ValidationError("identity case and published source result do not match")

    predecessor = (
        CareerAssertionRevision.objects.select_for_update()
        .filter(source_result=source_result)
        .order_by("-revision")
        .first()
    )
    if predecessor is None:
        if current_case.status != ReconciliationCase.Status.OPEN:
            raise ValidationError("resolved identity case has no career assertion")
        revision = 1
        decision = CareerAssertionRevision.Decision.APPROVE_LINK
        audit_action = "career.identity_link_approved"
    else:
        if current_case.status != ReconciliationCase.Status.RESOLVED:
            raise ValidationError("identity correction requires a resolved case")
        if predecessor.person_id == current_person.pk:
            raise ValidationError("identity correction must link a different person")
        revision = predecessor.revision + 1
        decision = CareerAssertionRevision.Decision.RELINK
        audit_action = "career.identity_link_corrected"

    assertion = CareerAssertionRevision.objects.create(
        organization=current_organization,
        source_result=source_result,
        person=current_person,
        reconciliation_case=current_case,
        revision=revision,
        predecessor=predecessor,
        decision=decision,
        authorization_basis_type=basis_type,
        authorization_basis_reference=reference,
        consent_grant=current_grant,
        authorization_captured_at=captured_at,
        reviewed_by=actor,
        source_payload_digest=source_result.payload_digest,
        decision_digest=request_digest,
    )
    if predecessor is None:
        current_case.status = ReconciliationCase.Status.RESOLVED
        current_case.resolved_by = actor
        current_case.resolved_at = timezone.now()
        current_case.save(update_fields=["status", "resolved_by", "resolved_at"])

    _finish_idempotency(record, assertion)
    audit_metadata = {
        "authorization_basis_type": basis_type,
        "case_id": str(current_case.pk),
        "organization_id": str(current_organization.pk),
        "person_id": str(current_person.pk),
        "revision": revision,
        "source_result_id": str(source_result.pk),
    }
    if current_grant is not None:
        audit_metadata["consent_grant_id"] = str(current_grant.pk)
    if predecessor is not None:
        audit_metadata["predecessor_assertion_id"] = str(predecessor.pk)
    record_audit_event(
        actor_id=actor.pk,
        action=audit_action,
        target_type="career_assertion_revision",
        target_id=str(assertion.pk),
        payload_digest=request_digest,
        metadata=audit_metadata,
    )
    return CareerReconciliationOutcome(assertion=assertion, replayed=False)
