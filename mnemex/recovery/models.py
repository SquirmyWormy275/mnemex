from __future__ import annotations

import hmac
import re
import uuid
from typing import Any, NoReturn

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models

from mnemex.recovery.services import (
    RecoveryManifestPayload,
    recovery_rehearsal_evidence_digest,
)

_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ISSUE_CODE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")


class ImmutableRecoveryQuerySet(models.QuerySet):
    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("recovery evidence is append-only")

    def delete(self) -> NoReturn:
        raise PermissionDenied("recovery evidence is append-only")


class RecoveryManifest(models.Model):
    """Immutable recovery dependencies captured before a backup rehearsal."""

    manifest_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    database_snapshot_identity = models.CharField(max_length=160)
    object_inventory_digest = models.CharField(max_length=64)
    object_count = models.PositiveBigIntegerField()
    required_mfa_key_versions = models.JSONField(default=list)
    required_notification_key_versions = models.JSONField(default=list)
    application_schema_version = models.CharField(max_length=160)
    environment_fingerprint = models.CharField(max_length=64)
    payload_digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableRecoveryQuerySet.as_manager()

    class Meta:
        app_label = "recovery"
        default_permissions = ("add", "view")
        ordering = ("-created_at", "manifest_id")
        indexes = [
            models.Index(
                fields=("environment_fingerprint", "-created_at"),
                name="recovery_manifest_env_idx",
            )
        ]

    def payload(self) -> RecoveryManifestPayload:
        return RecoveryManifestPayload(
            database_snapshot_identity=self.database_snapshot_identity,
            object_inventory_digest=self.object_inventory_digest,
            object_count=self.object_count,
            required_mfa_key_versions=tuple(self.required_mfa_key_versions),
            required_notification_key_versions=tuple(self.required_notification_key_versions),
            application_schema_version=self.application_schema_version,
            environment_fingerprint=self.environment_fingerprint,
            payload_digest=self.payload_digest,
        )

    def clean(self) -> None:
        super().clean()
        payload = self.payload()
        payload.verify()
        self.required_mfa_key_versions = list(payload.required_mfa_key_versions)
        self.required_notification_key_versions = list(payload.required_notification_key_versions)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise PermissionDenied("recovery manifests are append-only")
        self.full_clean()
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("recovery manifests are append-only")


class RecoveryRehearsalRecord(models.Model):
    """Immutable PII-free outcome from one disposable recovery rehearsal."""

    class Result(models.TextChoices):
        PASS = "pass", "Pass"
        FAIL = "fail", "Fail"

    record_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    manifest = models.ForeignKey(
        RecoveryManifest,
        on_delete=models.PROTECT,
        related_name="rehearsal_records",
    )
    result = models.CharField(max_length=8, choices=Result.choices)
    environment_fingerprint = models.CharField(max_length=64)
    issue_codes = models.JSONField(default=list, blank=True)
    normalized_lease_count = models.PositiveIntegerField(default=0)
    evidence_digest = models.CharField(max_length=64)
    observed_at = models.DateTimeField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableRecoveryQuerySet.as_manager()

    class Meta:
        app_label = "recovery"
        default_permissions = ("add", "view")
        ordering = ("-observed_at", "record_id")
        constraints = [
            models.UniqueConstraint(
                fields=("manifest", "observed_at", "evidence_digest"),
                name="unique_recovery_rehearsal_fact",
            )
        ]
        indexes = [
            models.Index(
                fields=("environment_fingerprint", "-observed_at"),
                name="recovery_record_env_idx",
            )
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if not _HEX_DIGEST.fullmatch(self.environment_fingerprint):
            errors["environment_fingerprint"] = "Expected a lowercase SHA-256 digest"
        if not _HEX_DIGEST.fullmatch(self.evidence_digest):
            errors["evidence_digest"] = "Expected a lowercase SHA-256 digest"
        if getattr(self, "manifest_id", None) and not hmac.compare_digest(
            self.environment_fingerprint,
            self.manifest.environment_fingerprint,
        ):
            errors["environment_fingerprint"] = "Rehearsal environment differs from manifest"
        if not isinstance(self.issue_codes, list) or any(
            not isinstance(code, str) or not _ISSUE_CODE.fullmatch(code)
            for code in self.issue_codes
        ):
            errors["issue_codes"] = "Use fixed PII-free recovery issue codes"
        elif self.issue_codes != sorted(set(self.issue_codes)):
            errors["issue_codes"] = "Recovery issue codes must be sorted and unique"
        if self.result == self.Result.PASS and self.issue_codes:
            errors["result"] = "Passing recovery evidence cannot contain issues"
        if self.result == self.Result.FAIL and not self.issue_codes:
            errors["result"] = "Failed recovery evidence requires an issue code"
        if getattr(self, "manifest_id", None) and not errors:
            expected_digest = recovery_rehearsal_evidence_digest(
                result=self.result,
                manifest_digest=self.manifest.payload_digest,
                environment_fingerprint=self.environment_fingerprint,
                object_count=self.manifest.object_count,
                normalized_lease_count=self.normalized_lease_count,
                issue_codes=self.issue_codes,
            )
            if not hmac.compare_digest(self.evidence_digest, expected_digest):
                errors["evidence_digest"] = "Recovery evidence digest does not match"
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise PermissionDenied("recovery rehearsal records are append-only")
        self.full_clean()
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("recovery rehearsal records are append-only")
