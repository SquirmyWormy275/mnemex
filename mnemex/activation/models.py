from __future__ import annotations

import hmac
import uuid
from typing import Any, NoReturn

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models

SAFE_SUMMARY_CODES = frozenset({"evidence.pending", "evidence.pass", "evidence.fail"})


class ActivationEvidenceQuerySet(models.QuerySet["ActivationEvidence"]):
    def bulk_create(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("Activation evidence is append-only")

    def bulk_update(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("Activation evidence is append-only")

    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("Activation evidence is append-only")

    def delete(self) -> NoReturn:
        raise PermissionDenied("Activation evidence is append-only")


class ActivationEvidence(models.Model):
    """Immutable, PII-free evidence for exactly one registered activation gate."""

    class Result(models.TextChoices):
        PENDING = "pending", "Pending"
        PASS = "pass", "Pass"
        FAIL = "fail", "Fail"

    evidence_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gate_id = models.CharField(max_length=48)
    result = models.CharField(max_length=12, choices=Result.choices)
    source = models.CharField(max_length=48)
    environment_fingerprint = models.CharField(max_length=64)
    evidence_time = models.DateTimeField()
    expires_at = models.DateTimeField()
    summary_code = models.CharField(max_length=120)
    payload_digest = models.CharField(max_length=64)
    recorded_at = models.DateTimeField(auto_now_add=True)

    objects = ActivationEvidenceQuerySet.as_manager()

    class Meta:
        app_label = "activation"
        default_permissions = ("add", "view")
        ordering = ("gate_id", "-evidence_time", "-recorded_at", "evidence_id")
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "gate_id",
                    "environment_fingerprint",
                    "evidence_time",
                    "payload_digest",
                ),
                name="unique_activation_evidence_fact",
            )
        ]
        indexes = [
            models.Index(
                fields=("environment_fingerprint", "gate_id", "-evidence_time"),
                name="activation_current_idx",
            )
        ]

    def clean(self) -> None:
        from .report import ACTIVATION_GATES, HEX_DIGEST, evidence_payload_digest

        errors: dict[str, str] = {}
        gate = ACTIVATION_GATES.get(self.gate_id)
        if gate is None:
            errors["gate_id"] = "Unknown activation gate"
        elif self.source != gate.evidence_source:
            errors["source"] = "Evidence source does not match the gate registry"
        if not HEX_DIGEST.fullmatch(self.environment_fingerprint):
            errors["environment_fingerprint"] = "Expected a lowercase SHA-256 digest"
        expected_summary = f"evidence.{self.result}"
        if self.summary_code not in SAFE_SUMMARY_CODES or self.summary_code != expected_summary:
            errors["summary_code"] = "Use the fixed redacted summary code for this result"
        if self.evidence_time and self.expires_at and self.expires_at <= self.evidence_time:
            errors["expires_at"] = "Evidence expiry must follow its observation time"
        if (
            gate is not None
            and self.evidence_time
            and self.expires_at
            and self.expires_at > self.evidence_time + gate.freshness
        ):
            errors["expires_at"] = "Evidence expiry exceeds the registered freshness window"
        if self.payload_digest and self.evidence_time and self.expires_at:
            expected_digest = evidence_payload_digest(self)
            if not hmac.compare_digest(self.payload_digest, expected_digest):
                errors["payload_digest"] = "Evidence payload digest does not match"
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise PermissionDenied("Activation evidence is append-only")
        if not self.payload_digest:
            from .report import evidence_payload_digest

            self.payload_digest = evidence_payload_digest(self)
        self.full_clean()
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("Activation evidence is append-only")
