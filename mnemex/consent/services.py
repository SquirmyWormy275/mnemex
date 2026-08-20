from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from mnemex.accounts.models import Account
from mnemex.consent.models import ConsentGrant, PublicProfileOptIn
from mnemex.foundation.services import record_audit_event
from mnemex.partners.models import PartnerClient
from mnemex.people.models import GuardianRelationship, Person


class ConsentDenied(PermissionError):
    """A disclosure or visibility action lacks current authority."""


FIELD_GROUP_FIELDS: dict[str, frozenset[str]] = {
    ConsentGrant.FieldGroup.BASIC_IDENTITY: frozenset({"display_name", "public_aliases"}),
    ConsentGrant.FieldGroup.LEGAL_IDENTITY: frozenset(
        {"legal_name", "birth_date", "federation_ids"}
    ),
    ConsentGrant.FieldGroup.CONTACT: frozenset({"email", "phone"}),
    ConsentGrant.FieldGroup.ELIGIBILITY_EVIDENCE: frozenset({"eligibility_claims"}),
    ConsentGrant.FieldGroup.OPERATIONAL_PREFERENCES: frozenset({"preferences"}),
    ConsentGrant.FieldGroup.CAREER_SUMMARY: frozenset({"career_summary"}),
}
PUBLIC_PROFILE_FIELDS = frozenset({"display_name", "public_aliases", "career_summary"})


def _authorize_subject_action(
    *,
    person: Person,
    acting_account: Account,
    guardian_relationship: GuardianRelationship | None,
) -> None:
    if not acting_account.is_active:
        raise ConsentDenied("acting account is not active")
    if person.age_classification == Person.AgeClassification.ADULT:
        if person.account_id != acting_account.account_id or guardian_relationship is not None:
            raise ConsentDenied("adult consent requires the subject account")
        return
    if person.age_classification == Person.AgeClassification.MINOR:
        if guardian_relationship is None:
            raise ConsentDenied("minor consent requires a guardian")
        if (
            guardian_relationship.guardian_account_id != acting_account.account_id
            or guardian_relationship.minor_person_id != person.person_id
            or not guardian_relationship.is_active
        ):
            raise ConsentDenied("minor consent requires active verified guardian authority")
        return
    raise ConsentDenied("age classification is required before consent")


def _validated_groups(groups: Sequence[str]) -> list[str]:
    normalized = list(dict.fromkeys(str(group) for group in groups))
    if not normalized or any(group not in FIELD_GROUP_FIELDS for group in normalized):
        raise ConsentDenied("consent contains an unsupported field group")
    return normalized


@transaction.atomic
def issue_consent_grant(
    *,
    person: Person,
    acting_account: Account,
    guardian_relationship: GuardianRelationship | None,
    recipient_client: PartnerClient,
    purpose: str,
    field_groups: Sequence[str],
    context_id: str,
    expires_at: datetime,
    policy_version: str,
    verification_threshold: str = "self_asserted",
) -> ConsentGrant:
    person = Person.objects.select_for_update().get(pk=person.pk)
    acting_account = Account.objects.select_for_update().get(pk=acting_account.pk)
    recipient_client = (
        PartnerClient.objects.select_for_update()
        .select_related("organization")
        .get(pk=recipient_client.pk)
    )
    if guardian_relationship is not None:
        guardian_relationship = GuardianRelationship.objects.select_for_update().get(
            pk=guardian_relationship.pk
        )
    _authorize_subject_action(
        person=person,
        acting_account=acting_account,
        guardian_relationship=guardian_relationship,
    )
    if not recipient_client.is_active:
        raise ConsentDenied("recipient client is not active")
    groups = _validated_groups(field_groups)
    if purpose not in recipient_client.allowed_purposes:
        raise ConsentDenied("recipient client is not allowed for this purpose")
    if not set(groups).issubset(set(recipient_client.allowed_field_groups)):
        raise ConsentDenied("recipient client is not allowed for a requested field group")
    if expires_at <= timezone.now():
        raise ConsentDenied("consent expiry must be in the future")
    if not context_id:
        raise ConsentDenied("consent requires an event or registration context")

    grant = ConsentGrant.objects.create(
        person=person,
        acting_account=acting_account,
        guardian_relationship=guardian_relationship,
        recipient_client=recipient_client,
        purpose=purpose,
        field_groups=groups,
        context_id=context_id,
        expires_at=expires_at,
        policy_version=policy_version,
        verification_threshold=verification_threshold,
    )
    digest = hashlib.sha256(
        f"{grant.grant_id}:{recipient_client.client_id}:{purpose}:{context_id}".encode()
    ).hexdigest()
    record_audit_event(
        actor_id=acting_account.account_id,
        action="consent.granted",
        target_type="consent_grant",
        target_id=str(grant.grant_id),
        payload_digest=digest,
        metadata={"policy_version": policy_version},
    )
    return grant


@transaction.atomic
def revoke_consent_grant(
    *, grant: ConsentGrant, acting_account: Account, reason: str
) -> ConsentGrant:
    locked = ConsentGrant.objects.select_for_update().get(pk=grant.pk)
    acting_account = Account.objects.select_for_update().get(pk=acting_account.pk)
    if not acting_account.is_active:
        raise ConsentDenied("acting account is not active")
    if locked.acting_account_id != acting_account.account_id:
        raise ConsentDenied("only the granting account may revoke this consent")
    if locked.revoked_at is None:
        locked.revoked_at = timezone.now()
        locked.revocation_reason = reason
        locked.revision = F("revision") + 1
        locked.save(update_fields=("revoked_at", "revocation_reason", "revision"))
        locked.refresh_from_db()
        digest = hashlib.sha256(f"{locked.grant_id}:{locked.revision}:revoked".encode()).hexdigest()
        record_audit_event(
            actor_id=acting_account.account_id,
            action="consent.revoked",
            target_type="consent_grant",
            target_id=str(locked.grant_id),
            payload_digest=digest,
            metadata={"policy_version": locked.policy_version},
        )
    grant.revoked_at = locked.revoked_at
    grant.revocation_reason = locked.revocation_reason
    grant.revision = locked.revision
    return locked


@transaction.atomic
def disclose_profile(
    *,
    grant: ConsentGrant,
    recipient_client: PartnerClient,
    purpose: str,
    context_id: str,
    available_fields: Mapping[str, Any],
) -> dict[str, Any]:
    current_grant = ConsentGrant.objects.select_for_update().get(pk=grant.pk)
    current_person = Person.objects.select_for_update().get(pk=current_grant.person_id)
    current_client = (
        PartnerClient.objects.select_for_update()
        .select_related("organization")
        .get(pk=current_grant.recipient_client_id)
    )
    if not current_grant.is_active:
        raise ConsentDenied("consent grant is not active")
    if current_person.status != Person.Status.ACTIVE:
        raise ConsentDenied("consent subject is not active")
    if current_grant.guardian_relationship_id is not None:
        current_relationship = GuardianRelationship.objects.select_for_update().get(
            pk=current_grant.guardian_relationship_id
        )
        if not current_relationship.is_active:
            raise ConsentDenied("consent guardian authority is not active")
    if (
        not current_client.is_active
        or current_grant.recipient_client_id != recipient_client.client_id
    ):
        raise ConsentDenied("consent recipient does not match")
    if current_grant.purpose != purpose or current_grant.context_id != context_id:
        raise ConsentDenied("consent purpose or context does not match")
    permitted = set().union(*(FIELD_GROUP_FIELDS[group] for group in current_grant.field_groups))
    return {key: value for key, value in available_fields.items() if key in permitted}


@transaction.atomic
def opt_in_public_profile(
    *,
    person: Person,
    acting_account: Account,
    guardian_relationship: GuardianRelationship | None,
    selected_fields: Sequence[str],
    policy_version: str,
) -> PublicProfileOptIn:
    person = Person.objects.select_for_update().get(pk=person.pk)
    acting_account = Account.objects.select_for_update().get(pk=acting_account.pk)
    if guardian_relationship is not None:
        guardian_relationship = GuardianRelationship.objects.select_for_update().get(
            pk=guardian_relationship.pk
        )
    _authorize_subject_action(
        person=person,
        acting_account=acting_account,
        guardian_relationship=guardian_relationship,
    )
    fields = list(dict.fromkeys(str(field) for field in selected_fields))
    if not fields or not set(fields).issubset(PUBLIC_PROFILE_FIELDS):
        raise ConsentDenied("public field selection contains a private or unsupported field")
    PublicProfileOptIn.objects.filter(person=person, revoked_at__isnull=True).update(
        revoked_at=timezone.now(),
        revocation_reason="superseded by a new public profile choice",
        revision=F("revision") + 1,
    )
    opt_in = PublicProfileOptIn.objects.create(
        person=person,
        acting_account=acting_account,
        guardian_relationship=guardian_relationship,
        selected_fields=fields,
        policy_version=policy_version,
    )
    digest = hashlib.sha256(
        f"{opt_in.opt_in_id}:{person.person_id}:{policy_version}".encode()
    ).hexdigest()
    record_audit_event(
        actor_id=acting_account.account_id,
        action="public-profile.opted-in",
        target_type="public_profile_opt_in",
        target_id=str(opt_in.opt_in_id),
        payload_digest=digest,
        metadata={"policy_version": policy_version},
    )
    return opt_in


@transaction.atomic
def public_profile_projection(
    *, person: Person, available_fields: Mapping[str, Any]
) -> dict[str, Any] | None:
    current_person = Person.objects.select_for_update().get(pk=person.pk)
    if current_person.status != Person.Status.ACTIVE:
        return None
    opt_in = (
        PublicProfileOptIn.objects.select_for_update()
        .filter(person=current_person, revoked_at__isnull=True)
        .order_by("-effective_at")
        .first()
    )
    if opt_in is None:
        return None
    if opt_in.guardian_relationship_id is not None:
        current_relationship = GuardianRelationship.objects.select_for_update().get(
            pk=opt_in.guardian_relationship_id
        )
        if not current_relationship.is_active:
            return None
    selected = set(opt_in.selected_fields).intersection(PUBLIC_PROFILE_FIELDS)
    return {key: value for key, value in available_fields.items() if key in selected}
