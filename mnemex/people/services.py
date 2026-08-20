from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import date
from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from mnemex.foundation.services import record_audit_event
from mnemex.people.crypto import IdentityCipher
from mnemex.people.models import GuardianRelationship, LegalIdentityClaim, Person

LEGAL_IDENTITY_FIELDS = frozenset(
    {"given_name", "middle_name", "family_name", "suffix", "birth_date"}
)
REQUIRED_LEGAL_IDENTITY_FIELDS = frozenset({"given_name", "family_name", "birth_date"})


def _validate_legal_identity_payload(payload: Mapping[str, Any]) -> None:
    keys = set(payload)
    unsupported = keys - LEGAL_IDENTITY_FIELDS
    if unsupported:
        raise ValueError(f"unsupported legal identity field: {sorted(unsupported)[0]}")
    missing = REQUIRED_LEGAL_IDENTITY_FIELDS - keys
    if missing:
        raise ValueError(f"missing legal identity field: {sorted(missing)[0]}")
    if any(value is not None and not isinstance(value, str) for value in payload.values()):
        raise ValueError("legal identity field values must be strings or null")
    birth_date = payload["birth_date"]
    if not isinstance(birth_date, str):
        raise ValueError("birth_date must be an ISO date string")
    parsed_birth_date = date.fromisoformat(birth_date)
    if parsed_birth_date > date.today():
        raise ValueError("birth_date cannot be in the future")


@transaction.atomic
def create_legal_identity_claim(
    *,
    person: Person,
    payload: Mapping[str, Any],
    lookup_value: str,
    source: str,
    policy_version: str,
    retention_rule: str,
    cipher: IdentityCipher,
) -> LegalIdentityClaim:
    _validate_legal_identity_payload(payload)
    sealed = cipher.encrypt(payload)
    return LegalIdentityClaim.objects.create(
        person=person,
        encrypted_payload=sealed.ciphertext,
        lookup_token=cipher.lookup_token(lookup_value),
        encryption_key_version=sealed.key_version,
        source=source,
        policy_version=policy_version,
        retention_rule=retention_rule,
    )


@transaction.atomic
def transition_person_to_adult(*, person: Person, policy_version: str, actor_id: UUID) -> Person:
    from mnemex.consent.models import ConsentGrant, PublicProfileOptIn

    locked = Person.objects.select_for_update().get(pk=person.pk)
    if locked.age_classification != Person.AgeClassification.MINOR:
        raise ValueError("only a classified minor can transition to adult")

    now = timezone.now()
    locked.age_classification = Person.AgeClassification.ADULT
    locked.age_policy_version = policy_version
    locked.age_transitioned_at = now
    locked.revision = F("revision") + 1
    locked.save(
        update_fields=(
            "age_classification",
            "age_policy_version",
            "age_transitioned_at",
            "revision",
            "updated_at",
        )
    )

    GuardianRelationship.objects.filter(minor_person=locked, revoked_at__isnull=True).update(
        verification_state=GuardianRelationship.VerificationState.REVOKED,
        revoked_at=now,
        revocation_reason="subject reached adulthood",
        revision=F("revision") + 1,
    )
    ConsentGrant.objects.filter(
        person=locked,
        guardian_relationship__isnull=False,
        revoked_at__isnull=True,
    ).update(
        revoked_at=now,
        revocation_reason="guardian authority ended at adulthood",
        revision=F("revision") + 1,
    )
    PublicProfileOptIn.objects.filter(
        person=locked,
        guardian_relationship__isnull=False,
        revoked_at__isnull=True,
    ).update(
        revoked_at=now,
        revocation_reason="guardian authority ended at adulthood",
        revision=F("revision") + 1,
    )

    digest = hashlib.sha256(f"{locked.person_id}:{policy_version}".encode()).hexdigest()
    record_audit_event(
        actor_id=actor_id,
        action="person.age-transitioned-to-adult",
        target_type="person",
        target_id=str(locked.person_id),
        payload_digest=digest,
        metadata={"policy_version": policy_version},
    )
    locked.refresh_from_db()
    return locked
