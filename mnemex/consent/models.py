from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone

from mnemex.accounts.models import Account
from mnemex.partners.models import PartnerClient
from mnemex.people.models import GuardianRelationship, Person


class ConsentGrant(models.Model):
    class FieldGroup(models.TextChoices):
        BASIC_IDENTITY = "identity.basic", "Basic identity"
        LEGAL_IDENTITY = "identity.legal", "Legal identity"
        CONTACT = "contact.registration", "Registration contact"
        ELIGIBILITY_EVIDENCE = "eligibility.evidence", "Eligibility evidence"
        OPERATIONAL_PREFERENCES = "preferences.operational", "Operational preferences"
        CAREER_SUMMARY = "career.summary", "Career summary"

    grant_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="consent_grants")
    acting_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="issued_consent_grants"
    )
    guardian_relationship = models.ForeignKey(
        GuardianRelationship,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="consent_grants",
    )
    recipient_client = models.ForeignKey(
        PartnerClient, on_delete=models.PROTECT, related_name="consent_grants"
    )
    purpose = models.CharField(max_length=120)
    field_groups = models.JSONField(default=list)
    context_id = models.CharField(max_length=160)
    verification_threshold = models.CharField(max_length=40, default="self_asserted")
    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.CharField(max_length=240, blank=True)
    policy_version = models.CharField(max_length=80)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        indexes = [
            models.Index(
                fields=("person", "recipient_client", "purpose", "revoked_at"),
                name="consent_disclosure_idx",
            )
        ]

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.expires_at > timezone.now()


class PublicProfileOptIn(models.Model):
    opt_in_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="public_profile_opt_ins"
    )
    acting_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="public_profile_opt_ins"
    )
    guardian_relationship = models.ForeignKey(
        GuardianRelationship,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="public_profile_opt_ins",
    )
    selected_fields = models.JSONField(default=list)
    policy_version = models.CharField(max_length=80)
    effective_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.CharField(max_length=240, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        indexes = [models.Index(fields=("person", "revoked_at"), name="public_opt_in_active_idx")]

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None
