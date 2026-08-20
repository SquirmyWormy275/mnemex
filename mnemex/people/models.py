from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone

from mnemex.accounts.models import Account


class Person(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        MERGED = "merged", "Merged"
        REDACTED = "redacted", "Redacted"

    class AgeClassification(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        MINOR = "minor", "Minor"
        ADULT = "adult", "Adult"

    person_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.OneToOneField(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="competitor_person",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="merged_people",
    )
    age_classification = models.CharField(
        max_length=20,
        choices=AgeClassification.choices,
        default=AgeClassification.UNKNOWN,
    )
    age_policy_version = models.CharField(max_length=80, blank=True)
    age_transitioned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        indexes = [models.Index(fields=("status", "age_classification"), name="person_state_idx")]


class Alias(models.Model):
    class ReviewState(models.TextChoices):
        UNREVIEWED = "unreviewed", "Unreviewed"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        DISPUTED = "disputed", "Disputed"

    alias_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="aliases")
    value = models.CharField(max_length=200)
    normalized_value = models.CharField(max_length=200)
    source = models.CharField(max_length=120)
    confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    review_state = models.CharField(
        max_length=20, choices=ReviewState.choices, default=ReviewState.UNREVIEWED
    )
    is_public = models.BooleanField(default=False)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("person", "normalized_value", "source"),
                name="unique_person_alias_source",
            )
        ]


class LegalIdentityClaim(models.Model):
    class VerificationState(models.TextChoices):
        UNVERIFIED = "unverified", "Unverified"
        SELF_ASSERTED = "self_asserted", "Self asserted"
        SOURCE_ASSERTED = "source_asserted", "Source asserted"
        VERIFIED = "verified", "Verified"
        EXPIRED = "expired", "Expired"
        REVOKED = "revoked", "Revoked"
        DISPUTED = "disputed", "Disputed"

    claim_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="legal_identity_claims"
    )
    encrypted_payload = models.BinaryField()
    lookup_token = models.CharField(max_length=64, db_index=True)
    encryption_key_version = models.PositiveIntegerField()
    source = models.CharField(max_length=120)
    verification_state = models.CharField(
        max_length=24,
        choices=VerificationState.choices,
        default=VerificationState.UNVERIFIED,
    )
    evidence_reference = models.CharField(max_length=240, blank=True)
    policy_version = models.CharField(max_length=80)
    retention_rule = models.CharField(max_length=160)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    disputed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        indexes = [
            models.Index(
                fields=("person", "verification_state"),
                name="legal_claim_state_idx",
            )
        ]


class GuardianRelationship(models.Model):
    class VerificationState(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"
        REVOKED = "revoked", "Revoked"

    relationship_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    guardian_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="guardian_relationships"
    )
    minor_person = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="guardian_relationships"
    )
    authority_basis = models.CharField(max_length=120)
    verification_state = models.CharField(
        max_length=20,
        choices=VerificationState.choices,
        default=VerificationState.PENDING,
    )
    evidence_reference = models.CharField(max_length=240, blank=True)
    jurisdiction = models.CharField(max_length=80)
    policy_version = models.CharField(max_length=80)
    effective_at = models.DateTimeField(default=timezone.now)
    verified_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        indexes = [
            models.Index(
                fields=("minor_person", "verification_state", "revoked_at"),
                name="guardian_authority_idx",
            )
        ]

    @property
    def is_active(self) -> bool:
        now = timezone.now()
        return (
            self.verification_state == self.VerificationState.VERIFIED
            and self.verified_at is not None
            and self.effective_at <= now
            and (self.expires_at is None or self.expires_at > now)
            and self.revoked_at is None
        )
