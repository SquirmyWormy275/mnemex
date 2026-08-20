"""Phase B contracts for identity, guardianship, consent, and disclosure."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from mnemex.accounts.authorization import Action, has_effective_role, may_perform
from mnemex.accounts.models import Account, PrivilegedRoleAssignment
from mnemex.consent.models import ConsentGrant
from mnemex.consent.services import (
    ConsentDenied,
    disclose_profile,
    issue_consent_grant,
    opt_in_public_profile,
    public_profile_projection,
    revoke_consent_grant,
)
from mnemex.foundation.models import AuditEvent
from mnemex.partners.models import PartnerClient, PartnerOrganization
from mnemex.people.crypto import IdentityCipher
from mnemex.people.models import GuardianRelationship, LegalIdentityClaim, Person
from mnemex.people.services import create_legal_identity_claim, transition_person_to_adult
from tests.factories import SyntheticDataFactory
from tests.mfa_helpers import enroll_account_mfa

pytestmark = pytest.mark.django_db


def _account(label: str, *, mfa: bool = False) -> Account:
    factory = SyntheticDataFactory()
    account = Account.objects.create_user(
        email=factory.email(label),
        password="correct horse battery staple",
    )
    if mfa:
        enroll_account_mfa(account)
    return account


def _client(label: str = "missoula") -> PartnerClient:
    organization = PartnerOrganization.objects.create(name=f"{label} synthetic show")
    return PartnerClient.objects.create(
        organization=organization,
        name=f"{label} registration client",
        environment=PartnerClient.Environment.SANDBOX,
        allowed_purposes=["show.registration"],
        allowed_field_groups=[
            ConsentGrant.FieldGroup.BASIC_IDENTITY,
            ConsentGrant.FieldGroup.LEGAL_IDENTITY,
            ConsentGrant.FieldGroup.CONTACT,
            ConsentGrant.FieldGroup.ELIGIBILITY_EVIDENCE,
            ConsentGrant.FieldGroup.OPERATIONAL_PREFERENCES,
            ConsentGrant.FieldGroup.CAREER_SUMMARY,
        ],
    )


def _expiry() -> timezone.datetime:
    return timezone.now() + timedelta(days=30)


def test_person_is_separate_from_login_account_and_private_by_default() -> None:
    competitor = _account("competitor")
    staff = _account("staff")

    person = Person.objects.create(
        account=competitor,
        age_classification=Person.AgeClassification.ADULT,
        age_policy_version="synthetic-policy-v1",
    )

    assert person.account == competitor
    assert not Person.objects.filter(account=staff).exists()
    assert not hasattr(person, "public_profile")
    assert person.revision == 1


def test_legal_identity_is_ciphertext_with_versioned_key_and_lookup_token() -> None:
    person = Person.objects.create(age_classification=Person.AgeClassification.ADULT)
    cipher = IdentityCipher(
        encryption_keys={1: b"e" * 32},
        active_version=1,
        lookup_key=b"l" * 32,
    )
    payload = {
        "given_name": "Synthetic",
        "family_name": "Competitor",
        "birth_date": "2000-01-01",
    }

    claim = create_legal_identity_claim(
        person=person,
        payload=payload,
        lookup_value="Synthetic Competitor|2000-01-01",
        source="synthetic-test",
        policy_version="synthetic-policy-v1",
        retention_rule="pilot-active-plus-approved-retention",
        cipher=cipher,
    )

    stored = bytes(claim.encrypted_payload)
    assert b"Synthetic" not in stored
    assert b"2000-01-01" not in stored
    assert claim.encryption_key_version == 1
    assert len(claim.lookup_token) == 64
    assert cipher.decrypt(stored, key_version=claim.encryption_key_version) == payload
    assert not any(
        field.name in {"legal_name", "date_of_birth", "birth_date"}
        for field in LegalIdentityClaim._meta.fields
    )

    with pytest.raises(ValueError, match="unsupported legal identity field"):
        create_legal_identity_claim(
            person=person,
            payload={**payload, "private_notes": "must never enter an identity claim"},
            lookup_value="Synthetic Competitor|2000-01-01",
            source="synthetic-test",
            policy_version="synthetic-policy-v1",
            retention_rule="pilot-active-plus-approved-retention",
            cipher=cipher,
        )


def test_minor_consent_requires_active_verified_guardian_authority() -> None:
    guardian = _account("guardian")
    minor = Person.objects.create(
        age_classification=Person.AgeClassification.MINOR,
        age_policy_version="synthetic-policy-v1",
    )
    client = _client()
    relationship = GuardianRelationship.objects.create(
        guardian_account=guardian,
        minor_person=minor,
        authority_basis="synthetic-parent",
        jurisdiction="US-MT",
        policy_version="synthetic-policy-v1",
    )

    with pytest.raises(ConsentDenied, match="verified guardian authority"):
        issue_consent_grant(
            person=minor,
            acting_account=guardian,
            guardian_relationship=relationship,
            recipient_client=client,
            purpose="show.registration",
            field_groups=[ConsentGrant.FieldGroup.BASIC_IDENTITY],
            context_id="synthetic-event-2027",
            expires_at=_expiry(),
            policy_version="synthetic-consent-v1",
        )

    relationship.verification_state = GuardianRelationship.VerificationState.VERIFIED
    relationship.verified_at = timezone.now()
    relationship.save(update_fields=("verification_state", "verified_at"))

    grant = issue_consent_grant(
        person=minor,
        acting_account=guardian,
        guardian_relationship=relationship,
        recipient_client=client,
        purpose="show.registration",
        field_groups=[ConsentGrant.FieldGroup.BASIC_IDENTITY],
        context_id="synthetic-event-2027",
        expires_at=_expiry(),
        policy_version="synthetic-consent-v1",
    )

    assert grant.guardian_relationship == relationship
    assert grant.is_active


def test_minor_cannot_self_issue_consent() -> None:
    minor_account = _account("minor")
    minor = Person.objects.create(
        account=minor_account,
        age_classification=Person.AgeClassification.MINOR,
    )

    with pytest.raises(ConsentDenied, match="guardian"):
        issue_consent_grant(
            person=minor,
            acting_account=minor_account,
            guardian_relationship=None,
            recipient_client=_client(),
            purpose="show.registration",
            field_groups=[ConsentGrant.FieldGroup.BASIC_IDENTITY],
            context_id="synthetic-event-2027",
            expires_at=_expiry(),
            policy_version="synthetic-consent-v1",
        )


def test_adult_can_issue_own_scoped_consent() -> None:
    competitor = _account("adult")
    person = Person.objects.create(
        account=competitor,
        age_classification=Person.AgeClassification.ADULT,
    )
    client = _client()

    grant = issue_consent_grant(
        person=person,
        acting_account=competitor,
        guardian_relationship=None,
        recipient_client=client,
        purpose="show.registration",
        field_groups=[
            ConsentGrant.FieldGroup.BASIC_IDENTITY,
            ConsentGrant.FieldGroup.OPERATIONAL_PREFERENCES,
        ],
        context_id="synthetic-event-2027",
        expires_at=_expiry(),
        policy_version="synthetic-consent-v1",
    )

    assert grant.is_active
    assert grant.guardian_relationship is None


def test_consent_and_public_visibility_lifecycle_is_audited_without_profile_values() -> None:
    competitor = _account("audit-lifecycle")
    person = Person.objects.create(
        account=competitor,
        age_classification=Person.AgeClassification.ADULT,
    )
    grant = issue_consent_grant(
        person=person,
        acting_account=competitor,
        guardian_relationship=None,
        recipient_client=_client("audit-lifecycle-client"),
        purpose="show.registration",
        field_groups=[ConsentGrant.FieldGroup.BASIC_IDENTITY],
        context_id="synthetic-event-2027",
        expires_at=_expiry(),
        policy_version="synthetic-consent-v1",
    )
    revoke_consent_grant(
        grant=grant,
        acting_account=competitor,
        reason="synthetic-user-revocation",
    )
    opt_in_public_profile(
        person=person,
        acting_account=competitor,
        guardian_relationship=None,
        selected_fields=["display_name"],
        policy_version="synthetic-public-v1",
    )

    events = list(AuditEvent.objects.filter(actor_id=competitor.account_id).order_by("occurred_at"))
    assert [event.action for event in events] == [
        "consent.granted",
        "consent.revoked",
        "public-profile.opted-in",
    ]
    serialized_metadata = str([event.metadata for event in events])
    assert "display_name" not in serialized_metadata
    assert "synthetic-user-revocation" not in serialized_metadata


def test_disclosure_returns_only_granted_fields_and_rejects_wrong_client() -> None:
    competitor = _account("disclosure")
    person = Person.objects.create(
        account=competitor,
        age_classification=Person.AgeClassification.ADULT,
    )
    client = _client("allowed")
    wrong_client = _client("wrong")
    grant = issue_consent_grant(
        person=person,
        acting_account=competitor,
        guardian_relationship=None,
        recipient_client=client,
        purpose="show.registration",
        field_groups=[ConsentGrant.FieldGroup.BASIC_IDENTITY],
        context_id="synthetic-event-2027",
        expires_at=_expiry(),
        policy_version="synthetic-consent-v1",
    )
    available = {
        "display_name": "Synthetic Competitor",
        "public_aliases": ["Synthetic C."],
        "email": "must-not-disclose@example.invalid",
        "legal_name": "Must Not Disclose",
        "preferences": {"handedness": "synthetic"},
    }

    disclosed = disclose_profile(
        grant=grant,
        recipient_client=client,
        purpose="show.registration",
        context_id="synthetic-event-2027",
        available_fields=available,
    )

    assert disclosed == {
        "display_name": "Synthetic Competitor",
        "public_aliases": ["Synthetic C."],
    }
    with pytest.raises(ConsentDenied, match="recipient"):
        disclose_profile(
            grant=grant,
            recipient_client=wrong_client,
            purpose="show.registration",
            context_id="synthetic-event-2027",
            available_fields=available,
        )

    revoke_consent_grant(grant=grant, acting_account=competitor, reason="synthetic-test")
    with pytest.raises(ConsentDenied, match="active"):
        disclose_profile(
            grant=grant,
            recipient_client=client,
            purpose="show.registration",
            context_id="synthetic-event-2027",
            available_fields=available,
        )


def test_disclosure_reloads_revocation_and_client_state_before_returning_fields() -> None:
    competitor = _account("stale-disclosure")
    person = Person.objects.create(
        account=competitor,
        age_classification=Person.AgeClassification.ADULT,
    )
    client = _client("stale-client")
    grant = issue_consent_grant(
        person=person,
        acting_account=competitor,
        guardian_relationship=None,
        recipient_client=client,
        purpose="show.registration",
        field_groups=[ConsentGrant.FieldGroup.BASIC_IDENTITY],
        context_id="synthetic-event-2027",
        expires_at=_expiry(),
        policy_version="synthetic-consent-v1",
    )
    stale_grant = ConsentGrant.objects.get(pk=grant.pk)

    ConsentGrant.objects.filter(pk=grant.pk).update(revoked_at=timezone.now())

    with pytest.raises(ConsentDenied, match="active"):
        disclose_profile(
            grant=stale_grant,
            recipient_client=client,
            purpose="show.registration",
            context_id="synthetic-event-2027",
            available_fields={"display_name": "Must Not Disclose"},
        )

    ConsentGrant.objects.filter(pk=grant.pk).update(revoked_at=None)
    stale_grant = ConsentGrant.objects.get(pk=grant.pk)
    PartnerClient.objects.filter(pk=client.pk).update(
        status=PartnerClient.Status.REVOKED,
        revoked_at=timezone.now(),
    )

    with pytest.raises(ConsentDenied, match="recipient"):
        disclose_profile(
            grant=stale_grant,
            recipient_client=client,
            purpose="show.registration",
            context_id="synthetic-event-2027",
            available_fields={"display_name": "Must Not Disclose"},
        )


def test_disclosure_stops_when_guardian_authority_or_person_state_changes() -> None:
    guardian = _account("live-authority-guardian")
    minor = Person.objects.create(age_classification=Person.AgeClassification.MINOR)
    relationship = GuardianRelationship.objects.create(
        guardian_account=guardian,
        minor_person=minor,
        authority_basis="synthetic-parent",
        verification_state=GuardianRelationship.VerificationState.VERIFIED,
        verified_at=timezone.now(),
        jurisdiction="US-MT",
        policy_version="synthetic-policy-v1",
    )
    client = _client("live-authority-client")
    grant = issue_consent_grant(
        person=minor,
        acting_account=guardian,
        guardian_relationship=relationship,
        recipient_client=client,
        purpose="show.registration",
        field_groups=[ConsentGrant.FieldGroup.BASIC_IDENTITY],
        context_id="synthetic-event-2027",
        expires_at=_expiry(),
        policy_version="synthetic-consent-v1",
    )

    GuardianRelationship.objects.filter(pk=relationship.pk).update(
        revoked_at=timezone.now(),
        verification_state=GuardianRelationship.VerificationState.REVOKED,
    )
    with pytest.raises(ConsentDenied, match="guardian authority"):
        disclose_profile(
            grant=grant,
            recipient_client=client,
            purpose="show.registration",
            context_id="synthetic-event-2027",
            available_fields={"display_name": "Must Not Disclose"},
        )

    GuardianRelationship.objects.filter(pk=relationship.pk).update(
        revoked_at=None,
        verification_state=GuardianRelationship.VerificationState.VERIFIED,
    )
    Person.objects.filter(pk=minor.pk).update(status=Person.Status.REDACTED)
    with pytest.raises(ConsentDenied, match="subject"):
        disclose_profile(
            grant=grant,
            recipient_client=client,
            purpose="show.registration",
            context_id="synthetic-event-2027",
            available_fields={"display_name": "Must Not Disclose"},
        )


def test_public_profile_is_private_by_default_and_rejects_private_fields() -> None:
    competitor = _account("public-profile")
    person = Person.objects.create(
        account=competitor,
        age_classification=Person.AgeClassification.ADULT,
    )
    available = {
        "display_name": "Synthetic Competitor",
        "career_summary": {"starts": 0},
        "email": "private@example.invalid",
    }

    assert public_profile_projection(person=person, available_fields=available) is None
    with pytest.raises(ConsentDenied, match="public field"):
        opt_in_public_profile(
            person=person,
            acting_account=competitor,
            guardian_relationship=None,
            selected_fields=["display_name", "email"],
            policy_version="synthetic-public-v1",
        )

    opt_in_public_profile(
        person=person,
        acting_account=competitor,
        guardian_relationship=None,
        selected_fields=["display_name", "career_summary"],
        policy_version="synthetic-public-v1",
    )

    assert public_profile_projection(person=person, available_fields=available) == {
        "display_name": "Synthetic Competitor",
        "career_summary": {"starts": 0},
    }


def test_minor_public_projection_rechecks_guardian_authority_and_person_state() -> None:
    guardian = _account("public-minor-guardian")
    minor = Person.objects.create(age_classification=Person.AgeClassification.MINOR)
    relationship = GuardianRelationship.objects.create(
        guardian_account=guardian,
        minor_person=minor,
        authority_basis="synthetic-parent",
        verification_state=GuardianRelationship.VerificationState.VERIFIED,
        verified_at=timezone.now(),
        jurisdiction="US-MT",
        policy_version="synthetic-policy-v1",
    )
    opt_in_public_profile(
        person=minor,
        acting_account=guardian,
        guardian_relationship=relationship,
        selected_fields=["display_name"],
        policy_version="synthetic-public-v1",
    )
    available = {"display_name": "Synthetic Minor"}

    assert public_profile_projection(person=minor, available_fields=available) == available

    GuardianRelationship.objects.filter(pk=relationship.pk).update(
        revoked_at=timezone.now(),
        verification_state=GuardianRelationship.VerificationState.REVOKED,
    )
    assert public_profile_projection(person=minor, available_fields=available) is None

    GuardianRelationship.objects.filter(pk=relationship.pk).update(
        revoked_at=None,
        verification_state=GuardianRelationship.VerificationState.VERIFIED,
    )
    Person.objects.filter(pk=minor.pk).update(status=Person.Status.REDACTED)
    assert public_profile_projection(person=minor, available_fields=available) is None


def test_age_transition_revokes_guardian_grants_and_public_opt_in() -> None:
    guardian = _account("transition-guardian")
    minor = Person.objects.create(
        age_classification=Person.AgeClassification.MINOR,
        age_policy_version="synthetic-minor-v1",
    )
    relationship = GuardianRelationship.objects.create(
        guardian_account=guardian,
        minor_person=minor,
        authority_basis="synthetic-parent",
        verification_state=GuardianRelationship.VerificationState.VERIFIED,
        verified_at=timezone.now(),
        jurisdiction="US-MT",
        policy_version="synthetic-minor-v1",
    )
    grant = issue_consent_grant(
        person=minor,
        acting_account=guardian,
        guardian_relationship=relationship,
        recipient_client=_client(),
        purpose="show.registration",
        field_groups=[ConsentGrant.FieldGroup.BASIC_IDENTITY],
        context_id="synthetic-event-2027",
        expires_at=_expiry(),
        policy_version="synthetic-consent-v1",
    )
    opt_in = opt_in_public_profile(
        person=minor,
        acting_account=guardian,
        guardian_relationship=relationship,
        selected_fields=["display_name"],
        policy_version="synthetic-public-v1",
    )

    transition_person_to_adult(
        person=minor,
        policy_version="synthetic-adult-v1",
        actor_id=guardian.account_id,
    )

    minor.refresh_from_db()
    grant.refresh_from_db()
    opt_in.refresh_from_db()
    relationship.refresh_from_db()
    assert minor.age_classification == Person.AgeClassification.ADULT
    assert minor.revision == 2
    assert grant.revoked_at is not None
    assert opt_in.revoked_at is not None
    assert relationship.revoked_at is not None


def test_privileged_role_is_ineffective_until_mfa_is_enrolled() -> None:
    staff = _account("results-manager")
    assignment = PrivilegedRoleAssignment.objects.create(
        account=staff,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        assigned_by=staff,
    )

    assert assignment.is_active
    assert not has_effective_role(staff, PrivilegedRoleAssignment.Role.RESULTS_MANAGER)

    enroll_account_mfa(staff)

    assert has_effective_role(staff, PrivilegedRoleAssignment.Role.RESULTS_MANAGER)

    stale_staff = Account.objects.get(pk=staff.pk)
    Account.objects.filter(pk=staff.pk).update(mfa_enrolled_at=None)

    assert not has_effective_role(stale_staff, PrivilegedRoleAssignment.Role.RESULTS_MANAGER)


@pytest.mark.parametrize(
    ("role", "allowed_action"),
    [
        (PrivilegedRoleAssignment.Role.RESULTS_MANAGER, Action.MANAGE_RESULTS),
        (PrivilegedRoleAssignment.Role.EXPORT_REVIEWER, Action.REVIEW_EXPORT),
        (PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER, Action.REVIEW_IDENTITY),
        (PrivilegedRoleAssignment.Role.PRIVACY_OFFICER, Action.RUN_PRIVACY_WORKFLOW),
        (PrivilegedRoleAssignment.Role.PARTNER_ADMINISTRATOR, Action.ADMINISTER_PARTNER),
    ],
)
def test_privileged_authorization_matrix_is_mfa_bound_and_role_specific(
    role: str, allowed_action: Action
) -> None:
    staff = _account(f"matrix-{role}", mfa=True)
    PrivilegedRoleAssignment.objects.create(account=staff, role=role, assigned_by=staff)

    assert may_perform(staff, allowed_action)
    for other_action in {
        Action.MANAGE_RESULTS,
        Action.REVIEW_EXPORT,
        Action.REVIEW_IDENTITY,
        Action.RUN_PRIVACY_WORKFLOW,
        Action.ADMINISTER_PARTNER,
    } - {allowed_action}:
        assert not may_perform(staff, other_action)


def test_privileged_role_scope_is_explicit_and_organization_bounded() -> None:
    staff = _account("scoped-results-manager", mfa=True)
    organization_a = PartnerOrganization.objects.create(name="Scoped synthetic show A")
    organization_b = PartnerOrganization.objects.create(name="Scoped synthetic show B")
    assignment = PrivilegedRoleAssignment.objects.create(
        account=staff,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        assigned_by=staff,
        scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
        organization=organization_a,
    )

    assert assignment.scope == PrivilegedRoleAssignment.Scope.ORGANIZATION
    assert may_perform(staff, Action.MANAGE_RESULTS, organization=organization_a)
    assert not may_perform(staff, Action.MANAGE_RESULTS, organization=organization_b)
    assert not may_perform(staff, Action.MANAGE_RESULTS)

    assignment.revoked_at = timezone.now()
    assignment.revocation_reason = "synthetic access removal"
    assignment.save(update_fields=["revoked_at", "revocation_reason"])
    assert not may_perform(staff, Action.MANAGE_RESULTS, organization=organization_a)


def test_platform_role_is_explicit_and_active_scope_duplicates_are_rejected() -> None:
    staff = _account("platform-results-manager", mfa=True)
    organization_a = PartnerOrganization.objects.create(name="Platform synthetic show A")
    organization_b = PartnerOrganization.objects.create(name="Platform synthetic show B")
    PrivilegedRoleAssignment.objects.create(
        account=staff,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        assigned_by=staff,
        scope=PrivilegedRoleAssignment.Scope.PLATFORM,
    )

    assert may_perform(staff, Action.MANAGE_RESULTS, organization=organization_a)
    assert may_perform(staff, Action.MANAGE_RESULTS, organization=organization_b)

    with pytest.raises(IntegrityError), transaction.atomic():
        PrivilegedRoleAssignment.objects.create(
            account=staff,
            role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
            assigned_by=staff,
            scope=PrivilegedRoleAssignment.Scope.PLATFORM,
        )

    organization_assignment = PrivilegedRoleAssignment.objects.create(
        account=staff,
        role=PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER,
        assigned_by=staff,
        scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
        organization=organization_a,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        PrivilegedRoleAssignment.objects.create(
            account=staff,
            role=PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER,
            assigned_by=staff,
            scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
            organization=organization_a,
        )
    organization_assignment.revoked_at = timezone.now()
    organization_assignment.save(update_fields=["revoked_at"])
    PrivilegedRoleAssignment.objects.create(
        account=staff,
        role=PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER,
        assigned_by=staff,
        scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
        organization=organization_a,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        PrivilegedRoleAssignment.objects.create(
            account=staff,
            role=PrivilegedRoleAssignment.Role.EXPORT_REVIEWER,
            assigned_by=staff,
            scope=PrivilegedRoleAssignment.Scope.PLATFORM,
            organization=organization_b,
        )


def test_competitor_and_guardian_authorization_is_subject_bounded() -> None:
    competitor = _account("matrix-competitor")
    other_competitor = _account("matrix-other")
    guardian = _account("matrix-guardian")
    own_person = Person.objects.create(
        account=competitor,
        age_classification=Person.AgeClassification.ADULT,
    )
    other_person = Person.objects.create(
        account=other_competitor,
        age_classification=Person.AgeClassification.ADULT,
    )
    minor = Person.objects.create(age_classification=Person.AgeClassification.MINOR)
    relationship = GuardianRelationship.objects.create(
        guardian_account=guardian,
        minor_person=minor,
        authority_basis="synthetic-parent",
        verification_state=GuardianRelationship.VerificationState.VERIFIED,
        verified_at=timezone.now(),
        jurisdiction="US-MT",
        policy_version="synthetic-policy-v1",
    )

    assert may_perform(competitor, Action.MANAGE_OWN_PROFILE, person=own_person)
    assert not may_perform(competitor, Action.MANAGE_OWN_PROFILE, person=other_person)
    assert may_perform(
        guardian,
        Action.MANAGE_GUARDIAN_PROFILE,
        person=minor,
        guardian_relationship=relationship,
    )
    assert not may_perform(
        guardian,
        Action.MANAGE_GUARDIAN_PROFILE,
        person=other_person,
        guardian_relationship=relationship,
    )
