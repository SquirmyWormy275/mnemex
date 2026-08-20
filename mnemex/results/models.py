from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, NoReturn

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models

from mnemex.accounts.models import Account
from mnemex.partners.models import PartnerOrganization
from mnemex.people.models import Person
from mnemex.schema import Discipline, ScoreType


def _mapping_field_map_digest(field_map: object) -> str:
    canonical = json.dumps(
        field_map,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class ImmutableSourceArtifactQuerySet(models.QuerySet["SourceArtifact"]):
    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("source artifacts are immutable")

    def delete(self) -> NoReturn:
        raise PermissionDenied("source artifacts are immutable")


class ImmutableArtifactObjectQuerySet(models.QuerySet["ArtifactObject"]):
    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("artifact object provenance is immutable")

    def delete(self) -> NoReturn:
        raise PermissionDenied("artifact object provenance is immutable")


class ArtifactObject(models.Model):
    """Durable registry row for one content-addressed private object."""

    object_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    digest = models.CharField(max_length=64)
    object_reference = models.CharField(max_length=500, unique=True)
    byte_size = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableArtifactObjectQuerySet.as_manager()

    class Meta:
        indexes = [models.Index(fields=("digest",), name="artifact_object_digest_idx")]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise PermissionDenied("artifact object provenance is immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("artifact object provenance is immutable")


class SourceArtifact(models.Model):
    """Private provenance manifest for a file upload or manual-entry batch."""

    class Kind(models.TextChoices):
        SPREADSHEET = "spreadsheet", "Spreadsheet"
        MANUAL_MANIFEST = "manual_manifest", "Manual-entry manifest"

    artifact_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization, on_delete=models.PROTECT, related_name="source_artifacts"
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    digest = models.CharField(max_length=64)
    original_name = models.CharField(max_length=240)
    content_type = models.CharField(max_length=160)
    byte_size = models.PositiveBigIntegerField()
    object_reference = models.CharField(max_length=500, blank=True)
    uploaded_by = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="uploaded_result_artifacts"
    )
    retention_class = models.CharField(max_length=80, default="results-source-pilot")
    received_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableSourceArtifactQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "kind", "digest"),
                name="unique_results_artifact_digest",
            )
        ]
        indexes = [
            models.Index(fields=("organization", "received_at"), name="result_artifact_org_idx"),
            models.Index(
                fields=(
                    "object_reference",
                    "digest",
                    "byte_size",
                    "received_at",
                    "artifact_id",
                ),
                name="artifact_source_lookup_idx",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise PermissionDenied("source artifacts are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("source artifacts are immutable")


class ArtifactObjectWriteQuerySet(models.QuerySet["ArtifactObjectWrite"]):
    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("artifact write state must use the lifecycle service")

    def delete(self) -> NoReturn:
        raise PermissionDenied("artifact write evidence is immutable")

    def bulk_create(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("artifact write creation must use the lifecycle service")

    def bulk_update(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("artifact write state must use the lifecycle service")


class ArtifactObjectWrite(models.Model):
    """One durable upload attempt against a shared content-addressed object."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        LINKED = "linked", "Linked"
        ABANDONED = "abandoned", "Abandoned"
        CLEANED = "cleaned", "Cleaned"
        PRESERVED = "preserved", "Preserved by another reference"
        BLOCKED = "blocked", "Blocked for recovery review"

    write_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization,
        on_delete=models.PROTECT,
        related_name="artifact_object_writes",
    )
    artifact_object = models.ForeignKey(
        ArtifactObject,
        on_delete=models.PROTECT,
        related_name="write_attempts",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    source_artifact = models.ForeignKey(
        SourceArtifact,
        on_delete=models.PROTECT,
        related_name="object_write_attempts",
        null=True,
        blank=True,
    )
    reconcile_after = models.DateTimeField()
    error_code = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    objects = ArtifactObjectWriteQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(
                fields=("status", "reconcile_after"),
                name="artifact_write_reconcile_idx",
            ),
            models.Index(
                fields=("organization", "created_at"),
                name="artifact_write_org_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status="active",
                        source_artifact__isnull=True,
                        resolved_at__isnull=True,
                        error_code="",
                    )
                    | models.Q(
                        status="linked",
                        source_artifact__isnull=False,
                        resolved_at__isnull=False,
                        error_code="",
                    )
                    | models.Q(
                        status__in=(
                            "abandoned",
                            "cleaned",
                            "preserved",
                            "blocked",
                        ),
                        source_artifact__isnull=True,
                        resolved_at__isnull=False,
                    )
                    & ~models.Q(error_code="")
                ),
                name="artifact_write_status_shape",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.status in (self.Status.ACTIVE, self.Status.LINKED) and self.error_code:
            raise ValidationError({"error_code": "active and linked writes cannot have errors"})
        if (
            self.status
            in (
                self.Status.ABANDONED,
                self.Status.CLEANED,
                self.Status.PRESERVED,
                self.Status.BLOCKED,
            )
            and not self.error_code
        ):
            raise ValidationError({"error_code": "resolved write attempts require an error code"})
        source_artifact = self.source_artifact
        if source_artifact is not None:
            if source_artifact.organization_id != self.organization_id:
                raise ValidationError(
                    {"source_artifact": "source artifact organization must match write attempt"}
                )
            artifact_object = self.artifact_object
            if (
                source_artifact.digest != artifact_object.digest
                or source_artifact.object_reference != artifact_object.object_reference
                or source_artifact.byte_size != artifact_object.byte_size
            ):
                raise ValidationError(
                    {"source_artifact": "source artifact must match the registered object"}
                )

    def save(self, *args: Any, **kwargs: Any) -> None:
        lifecycle_transition = bool(kwargs.pop("_lifecycle_transition", False))
        self.full_clean()
        if self._state.adding:
            if self.status != self.Status.ACTIVE:
                raise PermissionDenied("artifact writes must begin in the active state")
        else:
            if not lifecycle_transition:
                raise PermissionDenied("artifact write state must use the lifecycle service")
            current = type(self).objects.filter(pk=self.pk).first()
            if current is None:
                raise PermissionDenied("artifact write provenance is immutable")
            immutable_fields = ("organization_id", "artifact_object_id", "created_at")
            if any(getattr(self, field) != getattr(current, field) for field in immutable_fields):
                raise PermissionDenied("artifact write provenance is immutable")
            current_status = self.Status(current.status)
            target_status = self.Status(self.status)
            terminal_statuses = {
                self.Status.LINKED,
                self.Status.CLEANED,
                self.Status.PRESERVED,
                self.Status.BLOCKED,
            }
            if current_status in terminal_statuses:
                raise PermissionDenied("terminal artifact write evidence is immutable")
            allowed_transitions = {
                self.Status.ACTIVE: {
                    self.Status.ACTIVE,
                    self.Status.LINKED,
                    self.Status.ABANDONED,
                    self.Status.CLEANED,
                    self.Status.PRESERVED,
                    self.Status.BLOCKED,
                },
                self.Status.ABANDONED: {
                    self.Status.LINKED,
                    self.Status.CLEANED,
                    self.Status.PRESERVED,
                    self.Status.BLOCKED,
                },
            }
            if target_status not in allowed_transitions[current_status]:
                raise PermissionDenied("artifact write state transition is not allowed")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("artifact write evidence is immutable")


class MappingTemplateQuerySet(models.QuerySet["MappingTemplate"]):
    def update(self, **kwargs: Any) -> int:
        if set(kwargs) != {"is_active"} or not isinstance(kwargs["is_active"], bool):
            raise PermissionDenied("mapping template provenance is immutable")
        return super().update(**kwargs)

    def delete(self) -> NoReturn:
        raise PermissionDenied("mapping template provenance is immutable")


class MappingTemplate(models.Model):
    """Versioned mapping from canonical field names to source column names."""

    template_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization, on_delete=models.PROTECT, related_name="result_mapping_templates"
    )
    name = models.CharField(max_length=160)
    version = models.PositiveIntegerField()
    field_map = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="created_result_mapping_templates"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = MappingTemplateQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "name", "version"),
                name="unique_result_mapping_version",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} (v{self.version})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            current = type(self).objects.filter(pk=self.pk).first()
            if current is None:
                raise PermissionDenied("mapping template provenance is immutable")
            immutable_fields = (
                "organization_id",
                "name",
                "version",
                "field_map",
                "created_by_id",
            )
            if any(getattr(self, field) != getattr(current, field) for field in immutable_fields):
                raise PermissionDenied("mapping template provenance is immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("mapping template provenance is immutable")


class IngestionRunQuerySet(models.QuerySet["IngestionRun"]):
    def bulk_create(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("ingestion run provenance is immutable")

    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("ingestion run provenance is immutable")

    def delete(self) -> NoReturn:
        raise PermissionDenied("ingestion run provenance is immutable")


class IngestionRun(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        COMPLETED_WITH_QUARANTINE = (
            "completed_with_quarantine",
            "Completed with quarantined rows",
        )

    run_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization, on_delete=models.PROTECT, related_name="result_ingestion_runs"
    )
    artifact = models.ForeignKey(
        SourceArtifact, on_delete=models.PROTECT, related_name="ingestion_runs"
    )
    mapping_template = models.ForeignKey(
        MappingTemplate, on_delete=models.PROTECT, related_name="ingestion_runs"
    )
    field_map_digest = models.CharField(max_length=64, default="")
    source_sheet_name = models.CharField(max_length=128, blank=True, default="")
    source_partition_key = models.CharField(max_length=200, blank=True, default="")
    operator_key = models.CharField(max_length=200)
    request_digest = models.CharField(max_length=64)
    status = models.CharField(max_length=40, choices=Status.choices, default=Status.PROCESSING)
    total_rows = models.PositiveIntegerField(default=0)
    published_rows = models.PositiveIntegerField(default=0)
    quarantined_rows = models.PositiveIntegerField(default=0)
    duplicate_rows = models.PositiveIntegerField(default=0)
    conflict_rows = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="result_ingestion_runs"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = IngestionRunQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=(
                    "artifact",
                    "mapping_template",
                    "source_sheet_name",
                    "source_partition_key",
                ),
                name="unique_artifact_map_sheet_partition",
            )
        ]
        indexes = [
            models.Index(
                fields=("organization", "status", "created_at"), name="result_run_state_idx"
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.artifact_id and self.artifact.organization_id != self.organization_id:
            raise ValidationError(
                {"artifact": "artifact organization must match ingestion organization"}
            )
        if (
            self.mapping_template_id
            and self.mapping_template.organization_id != self.organization_id
        ):
            raise ValidationError(
                {"mapping_template": ("mapping organization must match ingestion organization")}
            )
        if self.mapping_template_id:
            expected_digest = _mapping_field_map_digest(self.mapping_template.field_map)
            if self.field_map_digest != expected_digest:
                raise ValidationError(
                    {
                        "field_map_digest": (
                            "field map digest must match the immutable mapping template"
                        )
                    }
                )

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self._state.adding and self.mapping_template_id and not self.field_map_digest:
            self.field_map_digest = _mapping_field_map_digest(self.mapping_template.field_map)
        self.full_clean()
        if not self._state.adding:
            current = type(self).objects.filter(pk=self.pk).first()
            if current is None:
                raise PermissionDenied("ingestion run provenance is immutable")
            immutable_fields = (
                "organization_id",
                "artifact_id",
                "mapping_template_id",
                "field_map_digest",
                "source_sheet_name",
                "source_partition_key",
                "operator_key",
                "request_digest",
                "created_by_id",
            )
            if any(getattr(self, field) != getattr(current, field) for field in immutable_fields):
                raise PermissionDenied("ingestion run provenance is immutable")
            operational_fields = (
                "status",
                "total_rows",
                "published_rows",
                "quarantined_rows",
                "duplicate_rows",
                "conflict_rows",
                "completed_at",
            )
            changed_operational = any(
                getattr(self, field) != getattr(current, field) for field in operational_fields
            )
            if current.status != self.Status.PROCESSING and changed_operational:
                raise PermissionDenied("completed ingestion run evidence is immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("ingestion run provenance is immutable")


class ImmutableStagedResultQuerySet(models.QuerySet["StagedResult"]):
    def bulk_create(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("staged result evidence is immutable")

    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("staged result evidence is immutable")

    def delete(self) -> NoReturn:
        raise PermissionDenied("staged result evidence is immutable")


class StagedResult(models.Model):
    class Outcome(models.TextChoices):
        PUBLISHED = "published", "Published"
        QUARANTINED = "quarantined", "Quarantined"
        DUPLICATE = "duplicate", "Duplicate"
        CONFLICT = "conflict", "Conflict"

    staged_result_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(IngestionRun, on_delete=models.PROTECT, related_name="staged_results")
    row_number = models.PositiveIntegerField()
    source_sheet_name = models.CharField(max_length=128, blank=True, default="")
    source_row_number = models.PositiveIntegerField(null=True, blank=True)
    source_result_id = models.CharField(max_length=200, blank=True)
    source_revision = models.PositiveIntegerField(null=True, blank=True)
    normalized_payload = models.JSONField(default=dict)
    payload_digest = models.CharField(max_length=64)
    validation_errors = models.JSONField(default=list)
    outcome = models.CharField(max_length=20, choices=Outcome.choices)
    proposed_person_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableStagedResultQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("run", "row_number"), name="unique_result_run_row")
        ]
        indexes = [models.Index(fields=("run", "outcome"), name="staged_result_outcome_idx")]

    def clean(self) -> None:
        super().clean()
        if self.run_id:
            if self.run.status != IngestionRun.Status.PROCESSING:
                raise ValidationError("staged rows can be added only while ingestion is processing")
            if self.source_sheet_name != self.run.source_sheet_name:
                raise ValidationError(
                    {"source_sheet_name": "source sheet must match the ingestion run"}
                )

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise PermissionDenied("staged result evidence is immutable")
        self.full_clean(exclude={"validation_errors", "proposed_person_ids"})
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("staged result evidence is immutable")


class ImmutablePublishedQuerySet(models.QuerySet["PublishedSourceResult"]):
    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("published source results are immutable")

    def delete(self) -> NoReturn:
        raise PermissionDenied("published source results are immutable")


class PublishedSourceResult(models.Model):
    """An immutable, deterministic-valid source row; identity may remain unresolved."""

    published_result_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization, on_delete=models.PROTECT, related_name="published_source_results"
    )
    source_result_id = models.CharField(max_length=200)
    source_revision = models.PositiveIntegerField()
    discipline = models.CharField(
        max_length=64, choices=[(item.value, item.name) for item in Discipline]
    )
    score_type = models.CharField(
        max_length=24, choices=[(item.value, item.name) for item in ScoreType]
    )
    normalized_payload = models.JSONField()
    payload_digest = models.CharField(max_length=64)
    artifact = models.ForeignKey(
        SourceArtifact, on_delete=models.PROTECT, related_name="published_source_results"
    )
    staged_result = models.OneToOneField(
        StagedResult, on_delete=models.PROTECT, related_name="published_source_result"
    )
    predecessor = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        related_name="successor",
        null=True,
        blank=True,
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="published_source_results",
        null=True,
        blank=True,
    )
    published_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutablePublishedQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(source_revision__gte=1, source_revision__lte=2_147_483_647),
                name="published_source_revision_range",
            ),
            models.UniqueConstraint(
                fields=("organization", "source_result_id", "source_revision"),
                name="unique_published_source_revision",
            ),
        ]
        indexes = [
            models.Index(fields=("discipline", "published_at"), name="published_discipline_idx")
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise PermissionDenied("published source results are immutable")
        self.full_clean()
        if self.artifact.organization_id != self.organization_id:
            raise ValidationError(
                {"artifact": "artifact organization must match published result organization"}
            )
        staged = self.staged_result
        if staged.run.organization_id != self.organization_id:
            raise ValidationError(
                {
                    "staged_result": (
                        "staged result organization must match published result organization"
                    )
                }
            )
        if staged.run.artifact_id != self.artifact_id:
            raise ValidationError(
                {"artifact": "published artifact must match the staged ingestion artifact"}
            )
        if (
            staged.outcome != StagedResult.Outcome.PUBLISHED
            or staged.source_result_id != self.source_result_id
            or staged.source_revision != self.source_revision
            or staged.payload_digest != self.payload_digest
            or staged.normalized_payload != self.normalized_payload
        ):
            raise ValidationError(
                {"staged_result": "published result must match its staged source evidence"}
            )
        if self.source_revision == 1:
            if self.predecessor_id is not None:
                raise ValidationError("source revision 1 cannot have a predecessor")
        else:
            predecessor = (
                type(self).objects.filter(pk=self.predecessor_id).first()
                if self.predecessor_id is not None
                else None
            )
            if (
                predecessor is None
                or predecessor.organization_id != self.organization_id
                or predecessor.source_result_id != self.source_result_id
                or predecessor.source_revision + 1 != self.source_revision
            ):
                raise ValidationError(
                    "source result revisions must name the contiguous predecessor"
                )
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("published source results are immutable")


class ReconciliationCase(models.Model):
    class CaseType(models.TextChoices):
        IDENTITY_UNRESOLVED = "identity_unresolved", "Identity unresolved"
        SOURCE_PAYLOAD_CONFLICT = "source_payload_conflict", "Source payload conflict"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"
        REJECTED = "rejected", "Rejected"

    case_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case_type = models.CharField(max_length=40, choices=CaseType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    staged_result = models.ForeignKey(
        StagedResult, on_delete=models.PROTECT, related_name="reconciliation_cases"
    )
    existing_published_result = models.ForeignKey(
        PublishedSourceResult,
        on_delete=models.PROTECT,
        related_name="reconciliation_cases",
        null=True,
        blank=True,
    )
    details = models.JSONField(default=dict)
    opened_at = models.DateTimeField(auto_now_add=True)
    resolved_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="resolved_result_cases",
        null=True,
        blank=True,
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=("case_type", "status", "opened_at"), name="result_case_queue_idx")
        ]

    def clean(self) -> None:
        super().clean()
        existing = self.existing_published_result if self.existing_published_result_id else None
        if (
            existing is not None
            and existing.organization_id != self.staged_result.run.organization_id
        ):
            raise ValidationError(
                {
                    "existing_published_result": (
                        "existing result organization must match staged result organization"
                    )
                }
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)
