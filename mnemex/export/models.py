from __future__ import annotations

import uuid
from typing import Any, NoReturn

from django.core.exceptions import PermissionDenied
from django.db import models

from mnemex.accounts.models import Account
from mnemex.career.models import CareerAssertionRevision
from mnemex.export.contract import EVIDENCE_SNAPSHOT_SOURCE_SCHEMA_VERSION, utc_iso
from mnemex.partners.models import PartnerOrganization


class ImmutableExportQuerySet(models.QuerySet):
    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("export records are immutable")

    def delete(self) -> NoReturn:
        raise PermissionDenied("export records are immutable")


class ExportEligibilityRevision(models.Model):
    class Decision(models.TextChoices):
        ELIGIBLE = "eligible", "Eligible"
        REJECTED = "rejected", "Rejected"

    eligibility_revision_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization,
        on_delete=models.PROTECT,
        related_name="export_eligibility_revisions",
    )
    career_assertion = models.ForeignKey(
        CareerAssertionRevision,
        on_delete=models.PROTECT,
        related_name="export_eligibility_revisions",
    )
    revision = models.PositiveIntegerField()
    predecessor = models.OneToOneField(
        "self", on_delete=models.PROTECT, related_name="successor", null=True, blank=True
    )
    decision = models.CharField(max_length=16, choices=Decision.choices)
    reason = models.CharField(max_length=240)
    reviewed_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="reviewed_export_eligibility_revisions",
    )
    decision_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableExportQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(revision__gte=1), name="export_eligibility_revision_positive"
            ),
            models.UniqueConstraint(
                fields=("career_assertion", "revision"),
                name="unique_export_eligibility_revision",
            ),
        ]
        indexes = [
            models.Index(
                fields=("organization", "decision", "created_at"),
                name="export_eligibility_state_idx",
            )
        ]

    @property
    def is_current(self) -> bool:
        return not type(self).objects.filter(predecessor_id=self.pk).exists()

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise PermissionDenied("export eligibility revisions are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("export eligibility revisions are immutable")


class EvidenceSnapshotManifest(models.Model):
    snapshot_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization,
        on_delete=models.PROTECT,
        related_name="evidence_snapshot_manifests",
    )
    schema_version = models.CharField(
        max_length=80, default=EVIDENCE_SNAPSHOT_SOURCE_SCHEMA_VERSION
    )
    source_id = models.CharField(max_length=128)
    cutoff = models.DateField()
    captured_at = models.DateTimeField()
    rows = models.JSONField(default=list)
    exclusions = models.JSONField(default=list)
    source_digest = models.CharField(max_length=64)
    request_digest = models.CharField(max_length=64)
    reviewed_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="generated_evidence_snapshot_manifests",
    )
    predecessor = models.OneToOneField(
        "self", on_delete=models.PROTECT, related_name="successor", null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableExportQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "source_id"), name="unique_evidence_snapshot_source"
            )
        ]
        indexes = [
            models.Index(
                fields=("organization", "cutoff", "created_at"),
                name="evidence_snapshot_org_idx",
            )
        ]

    @property
    def envelope(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "cutoff": self.cutoff.isoformat(),
            "cutoff_semantics": "exclusive-utc-date",
            "captured_at": utc_iso(self.captured_at),
            "rows": self.rows,
            "source_digest": self.source_digest,
        }

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise PermissionDenied("evidence snapshot manifests are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("evidence snapshot manifests are immutable")
