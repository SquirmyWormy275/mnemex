from __future__ import annotations

import uuid
from typing import Any, ClassVar, NoReturn

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

from mnemex.accounts.models import Account
from mnemex.partners.models import PartnerOrganization
from mnemex.results.models import IngestionRun, SourceArtifact

SHA256_VALIDATOR = RegexValidator(
    regex=r"^[0-9a-f]{64}$", message="Enter a lowercase SHA-256 digest."
)
CLAIM_TOKEN_VALIDATOR = RegexValidator(
    regex=r"^[0-9a-f]{64}$", message="Enter an opaque 64-character claim token."
)
MAX_LEGACY_APPLY_CHUNK_ROWS = 250


class ImmutableEvidenceQuerySet(models.QuerySet):
    def bulk_create(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("legacy migration evidence is immutable")

    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("legacy migration evidence is immutable")

    def delete(self) -> NoReturn:
        raise PermissionDenied("legacy migration evidence is immutable")


class ImmutableEvidenceModel(models.Model):
    evidence_label: ClassVar[str] = "legacy migration evidence"

    class Meta:
        abstract = True
        default_permissions = ("add", "view")

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise PermissionDenied(f"{self.evidence_label} is immutable")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied(f"{self.evidence_label} is immutable")


class OperationalRunQuerySet(models.QuerySet["LegacyMigrationRun"]):
    def bulk_create(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("legacy migration run provenance is immutable")

    def bulk_update(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("legacy migration run provenance is immutable")

    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("legacy migration run provenance is immutable")

    def delete(self) -> NoReturn:
        raise PermissionDenied("legacy migration runs cannot be deleted")


class OperationalJobQuerySet(models.QuerySet["LegacyMigrationJob"]):
    def bulk_create(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("legacy migration job transitions are service-owned")

    def bulk_update(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("legacy migration job transitions are service-owned")

    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("legacy migration job transitions are service-owned")

    def delete(self) -> NoReturn:
        raise PermissionDenied("legacy migration jobs cannot be deleted")


class OperationalCheckpointQuerySet(models.QuerySet["LegacyMigrationCheckpoint"]):
    def bulk_create(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("legacy migration checkpoint evidence is immutable")

    def bulk_update(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("legacy migration checkpoint evidence is immutable")

    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("legacy migration checkpoint evidence is immutable")

    def delete(self) -> NoReturn:
        raise PermissionDenied("legacy migration checkpoint evidence is immutable")


class LegacySourceInventory(ImmutableEvidenceModel):
    """Immutable tenant and rights manifest for one private source workbook."""

    evidence_label = "legacy source inventory"

    inventory_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization,
        on_delete=models.PROTECT,
        related_name="legacy_source_inventories",
    )
    artifact = models.OneToOneField(
        SourceArtifact, on_delete=models.PROTECT, related_name="legacy_source_inventory"
    )
    source_namespace = models.CharField(max_length=120, default="legacy-results")
    source_key = models.CharField(max_length=200)
    data_rights_reference = models.CharField(max_length=240)
    parser_version = models.CharField(max_length=80)
    manifest_digest = models.CharField(max_length=64, validators=[SHA256_VALIDATOR])
    created_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="created_legacy_source_inventories",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableEvidenceQuerySet.as_manager()

    class Meta(ImmutableEvidenceModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "source_namespace", "source_key"),
                name="uniq_legacy_source_key",
            )
        ]
        indexes = [
            models.Index(fields=("organization", "created_at"), name="legacy_inventory_org_idx")
        ]

    def clean(self) -> None:
        super().clean()
        if self.artifact_id and self.artifact.organization_id != self.organization_id:
            raise ValidationError(
                {"artifact": "artifact organization must match inventory organization"}
            )


class LegacyMigrationRun(models.Model):
    """Mutable operational state bound to immutable source and plan evidence."""

    class State(models.TextChoices):
        DISCOVERED = "discovered", "Discovered"
        CONFIGURED = "configured", "Configured"
        DRY_RUN_COMPLETE = "dry_run_complete", "Dry run complete"
        APPROVED = "approved", "Approved"
        APPLYING = "applying", "Applying"
        COMPLETED = "completed", "Completed"
        WITHDRAWN = "withdrawn", "Withdrawn"
        FAILED = "failed", "Failed"

    run_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization,
        on_delete=models.PROTECT,
        related_name="legacy_migration_runs",
    )
    inventory = models.ForeignKey(
        LegacySourceInventory, on_delete=models.PROTECT, related_name="migration_runs"
    )
    run_version = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    ruleset_version = models.CharField(max_length=80)
    state = models.CharField(max_length=32, choices=State.choices, default=State.DISCOVERED)
    plan_digest = models.CharField(
        max_length=64, validators=[SHA256_VALIDATOR], blank=True, default=""
    )
    source_state_digest = models.CharField(
        max_length=64, validators=[SHA256_VALIDATOR], blank=True, default=""
    )
    dry_run_manifest_digest = models.CharField(
        max_length=64, validators=[SHA256_VALIDATOR], blank=True, default=""
    )
    total_sheets = models.PositiveIntegerField(default=0)
    included_sheets = models.PositiveIntegerField(default=0)
    ignored_sheets = models.PositiveIntegerField(default=0)
    total_rows = models.PositiveIntegerField(default=0)
    candidate_rows = models.PositiveIntegerField(default=0)
    ignored_rows = models.PositiveIntegerField(default=0)
    publishable_rows = models.PositiveIntegerField(default=0)
    quarantined_rows = models.PositiveIntegerField(default=0)
    duplicate_rows = models.PositiveIntegerField(default=0)
    conflict_rows = models.PositiveIntegerField(default=0)
    applied_rows = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="created_legacy_migration_runs"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OperationalRunQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("inventory", "run_version"), name="uniq_legacy_run_version"
            )
        ]
        indexes = [
            models.Index(
                fields=("organization", "state", "created_at"),
                name="legacy_run_state_idx",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.inventory_id and self.inventory.organization_id != self.organization_id:
            raise ValidationError(
                {"inventory": "inventory organization must match run organization"}
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        if not self._state.adding:
            current = type(self).objects.filter(pk=self.pk).first()
            if current is None:
                raise PermissionDenied("legacy migration run provenance is immutable")
            immutable_fields = (
                "organization_id",
                "inventory_id",
                "run_version",
                "ruleset_version",
                "created_by_id",
            )
            if any(getattr(self, field) != getattr(current, field) for field in immutable_fields):
                raise PermissionDenied("legacy migration run provenance is immutable")
            write_once_digest_fields = (
                "plan_digest",
                "source_state_digest",
                "dry_run_manifest_digest",
            )
            if any(
                getattr(current, field) and getattr(self, field) != getattr(current, field)
                for field in write_once_digest_fields
            ):
                raise PermissionDenied("legacy migration run provenance is immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("legacy migration runs cannot be deleted")


class LegacyWorksheetPlan(ImmutableEvidenceModel):
    class Visibility(models.TextChoices):
        VISIBLE = "visible", "Visible"
        HIDDEN = "hidden", "Hidden"
        VERY_HIDDEN = "very_hidden", "Very hidden"

    class Disposition(models.TextChoices):
        INCLUDED = "included", "Included"
        IGNORED = "ignored", "Ignored"

    evidence_label = "legacy worksheet plan"

    worksheet_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization,
        on_delete=models.PROTECT,
        related_name="legacy_worksheet_plans",
    )
    run = models.ForeignKey(LegacyMigrationRun, on_delete=models.PROTECT, related_name="worksheets")
    sheet_index = models.PositiveIntegerField()
    sheet_name = models.CharField(max_length=255)
    visibility = models.CharField(
        max_length=16, choices=Visibility.choices, default=Visibility.VISIBLE
    )
    max_row = models.PositiveIntegerField(default=0)
    max_column = models.PositiveIntegerField(default=0)
    disposition = models.CharField(max_length=16, choices=Disposition.choices)
    ignore_reason = models.CharField(max_length=240, blank=True)
    metadata_digest = models.CharField(max_length=64, validators=[SHA256_VALIDATOR])
    header_candidates = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableEvidenceQuerySet.as_manager()

    class Meta(ImmutableEvidenceModel.Meta):
        ordering = ("sheet_index", "worksheet_id")
        constraints = [
            models.UniqueConstraint(fields=("run", "sheet_index"), name="uniq_legacy_sheet_index"),
            models.UniqueConstraint(fields=("run", "sheet_name"), name="uniq_legacy_sheet_name"),
        ]
        indexes = [
            models.Index(fields=("organization", "disposition"), name="legacy_sheet_disp_idx")
        ]

    def clean(self) -> None:
        super().clean()
        if self.run_id and self.run.organization_id != self.organization_id:
            raise ValidationError({"run": "run organization must match worksheet organization"})
        if self.disposition == self.Disposition.IGNORED and not self.ignore_reason.strip():
            raise ValidationError({"ignore_reason": "ignored worksheets require a reason"})
        if self.disposition == self.Disposition.INCLUDED and self.ignore_reason:
            raise ValidationError(
                {"ignore_reason": "included worksheets cannot have an ignore reason"}
            )


class LegacyTablePlan(ImmutableEvidenceModel):
    evidence_label = "legacy table plan"

    table_plan_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization, on_delete=models.PROTECT, related_name="legacy_table_plans"
    )
    run = models.ForeignKey(
        LegacyMigrationRun, on_delete=models.PROTECT, related_name="table_plans"
    )
    worksheet = models.ForeignKey(
        LegacyWorksheetPlan, on_delete=models.PROTECT, related_name="table_plans"
    )
    label = models.CharField(max_length=160)
    header_row = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    start_row = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    end_row = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    start_column = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    end_column = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    mapping_rules = models.JSONField(default=dict)
    mapping_digest = models.CharField(max_length=64, validators=[SHA256_VALIDATOR])
    created_by = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="created_legacy_table_plans"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableEvidenceQuerySet.as_manager()

    class Meta(ImmutableEvidenceModel.Meta):
        ordering = (
            "worksheet__sheet_index",
            "start_row",
            "start_column",
            "table_plan_id",
        )
        constraints = [
            models.UniqueConstraint(fields=("worksheet", "label"), name="uniq_legacy_table_label"),
            models.CheckConstraint(
                condition=models.Q(end_row__gte=models.F("start_row")),
                name="legacy_table_row_bounds",
            ),
            models.CheckConstraint(
                condition=models.Q(end_column__gte=models.F("start_column")),
                name="legacy_table_col_bounds",
            ),
            models.CheckConstraint(
                condition=models.Q(header_row__gte=models.F("start_row"))
                & models.Q(header_row__lte=models.F("end_row")),
                name="legacy_table_header_bounds",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.run_id and self.run.organization_id != self.organization_id:
            raise ValidationError({"run": "run organization must match table organization"})
        if self.worksheet_id:
            if self.worksheet.run_id != self.run_id:
                raise ValidationError({"worksheet": "worksheet run must match table run"})
            if self.worksheet.organization_id != self.organization_id:
                raise ValidationError(
                    {"worksheet": "worksheet organization must match table organization"}
                )
            if self.worksheet.disposition != LegacyWorksheetPlan.Disposition.INCLUDED:
                raise ValidationError({"worksheet": "table plans require an included worksheet"})
        if self.end_row < self.start_row:
            raise ValidationError({"end_row": "end row must be at or after start row"})
        if self.end_column < self.start_column:
            raise ValidationError({"end_column": "end column must be at or after start column"})
        if not self.start_row <= self.header_row <= self.end_row:
            raise ValidationError({"header_row": "header row must be inside the table region"})


class LegacyMigrationRowPreview(ImmutableEvidenceModel):
    """One no-write classification tied to exact physical source coordinates."""

    class Classification(models.TextChoices):
        PUBLISHABLE = "publishable", "Publishable"
        QUARANTINED = "quarantined", "Quarantined"
        DUPLICATE = "duplicate", "Duplicate"
        CONFLICT = "conflict", "Conflict"
        IGNORED = "ignored", "Ignored"

    evidence_label = "legacy migration row preview"

    preview_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization,
        on_delete=models.PROTECT,
        related_name="legacy_migration_row_previews",
    )
    run = models.ForeignKey(
        LegacyMigrationRun, on_delete=models.PROTECT, related_name="row_previews"
    )
    table_plan = models.ForeignKey(
        LegacyTablePlan, on_delete=models.PROTECT, related_name="row_previews"
    )
    source_sheet_index = models.PositiveIntegerField()
    source_row_number = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    source_column_start = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    source_column_end = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    canonical_payload = models.JSONField(default=dict)
    payload_digest = models.CharField(max_length=64, validators=[SHA256_VALIDATOR])
    classification = models.CharField(max_length=20, choices=Classification.choices)
    validation_errors = models.JSONField(default=list, blank=True)
    source_state_digest = models.CharField(max_length=64, validators=[SHA256_VALIDATOR])
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableEvidenceQuerySet.as_manager()

    class Meta(ImmutableEvidenceModel.Meta):
        ordering = (
            "source_sheet_index",
            "source_row_number",
            "source_column_start",
            "preview_id",
        )
        constraints = [
            models.UniqueConstraint(
                fields=("run", "table_plan", "source_row_number"),
                name="uniq_legacy_preview_row",
            ),
            models.CheckConstraint(
                condition=models.Q(source_column_end__gte=models.F("source_column_start")),
                name="legacy_preview_col_bounds",
            ),
        ]
        indexes = [models.Index(fields=("run", "classification"), name="legacy_preview_class_idx")]

    def clean(self) -> None:
        super().clean()
        if self.run_id and self.run.organization_id != self.organization_id:
            raise ValidationError({"run": "run organization must match preview organization"})
        if self.table_plan_id:
            if self.table_plan.run_id != self.run_id:
                raise ValidationError({"table_plan": "table plan run must match preview run"})
            if self.table_plan.organization_id != self.organization_id:
                raise ValidationError(
                    {"table_plan": "table plan organization must match preview organization"}
                )
            if self.source_sheet_index != self.table_plan.worksheet.sheet_index:
                raise ValidationError(
                    {"source_sheet_index": "source sheet index must match the table worksheet"}
                )
            if not self.table_plan.start_row <= self.source_row_number <= self.table_plan.end_row:
                raise ValidationError(
                    {"source_row_number": "source row must be inside the table region"}
                )
        if self.source_column_end < self.source_column_start:
            raise ValidationError(
                {"source_column_end": "source column end must not precede its start"}
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self._state.adding:
            self.full_clean()
            if self.run.state != LegacyMigrationRun.State.CONFIGURED:
                raise PermissionDenied("legacy migration preview intake is closed")
        super().save(*args, **kwargs)


class LegacyMigrationJob(models.Model):
    """Mutable execution state with immutable tenant/run provenance."""

    class Kind(models.TextChoices):
        DRY_RUN = "dry_run", "Dry run"
        APPLY = "apply", "Apply"
        RECONCILE = "reconcile", "Reconcile"
        WITHDRAW = "withdraw", "Withdraw"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        RETRY_WAIT = "retry_wait", "Retry wait"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    job_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization,
        on_delete=models.PROTECT,
        related_name="legacy_migration_jobs",
    )
    run = models.ForeignKey(LegacyMigrationRun, on_delete=models.PROTECT, related_name="jobs")
    job_kind = models.CharField(max_length=20, choices=Kind.choices)
    job_sequence = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    requested_manifest_digest = models.CharField(
        max_length=64, validators=[SHA256_VALIDATOR], blank=True
    )
    request_rationale = models.CharField(max_length=500, blank=True)
    chunk_size = models.PositiveIntegerField(default=MAX_LEGACY_APPLY_CHUNK_ROWS)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5, validators=[MinValueValidator(1)])
    available_at = models.DateTimeField(default=timezone.now)
    claim_token = models.CharField(max_length=64, validators=[CLAIM_TOKEN_VALIDATOR], blank=True)
    claim_owner = models.CharField(max_length=120, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    claim_generation = models.PositiveBigIntegerField(default=0)
    next_checkpoint_sequence = models.PositiveIntegerField(default=1)
    last_error_code = models.CharField(max_length=80, blank=True)
    last_error_message = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="created_legacy_migration_jobs"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OperationalJobQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("run", "job_kind", "job_sequence"),
                name="uniq_legacy_job_sequence",
            ),
            models.UniqueConstraint(
                fields=("run", "job_kind", "requested_manifest_digest", "chunk_size"),
                condition=models.Q(
                    job_kind="apply",
                    status__in=("pending", "running", "retry_wait"),
                ),
                name="uniq_active_legacy_job_req",
            ),
            models.CheckConstraint(
                condition=models.Q(chunk_size__gte=1)
                & models.Q(chunk_size__lte=MAX_LEGACY_APPLY_CHUNK_ROWS),
                name="legacy_job_chunk_bounds",
            ),
            models.CheckConstraint(
                condition=models.Q(max_attempts__gte=1),
                name="legacy_job_max_attempts",
            ),
            models.CheckConstraint(
                condition=models.Q(failure_count__lte=models.F("max_attempts")),
                name="legacy_job_failures_lte_max",
            ),
            models.CheckConstraint(
                condition=models.Q(attempt_count=models.F("claim_generation")),
                name="legacy_job_claim_counter_sync",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status="running",
                        claim_token__gt="",
                        claim_owner__gt="",
                        heartbeat_at__isnull=False,
                        lease_expires_at__isnull=False,
                    )
                    | models.Q(
                        ~models.Q(status="running"),
                        claim_token="",
                        claim_owner="",
                        heartbeat_at__isnull=True,
                        lease_expires_at__isnull=True,
                    )
                ),
                name="legacy_job_claim_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(job_kind="apply", requested_manifest_digest__gt="")
                    | ~models.Q(job_kind="apply")
                ),
                name="legacy_apply_manifest_shape",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(job_kind="apply", request_rationale__gt="")
                    | ~models.Q(job_kind="apply")
                ),
                name="legacy_apply_rationale_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("organization", "status", "created_at"),
                name="legacy_job_state_idx",
            ),
            models.Index(
                fields=("job_kind", "status", "available_at", "created_at"),
                name="legacy_job_claim_idx",
            ),
            models.Index(
                fields=("job_kind", "status", "lease_expires_at"),
                name="legacy_job_lease_idx",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.run_id and self.run.organization_id != self.organization_id:
            raise ValidationError({"run": "run organization must match job organization"})
        if self.job_kind == self.Kind.APPLY and not self.requested_manifest_digest:
            raise ValidationError(
                {"requested_manifest_digest": "apply job requires an approved manifest digest"}
            )
        if self.job_kind == self.Kind.APPLY and not self.request_rationale.strip():
            raise ValidationError({"request_rationale": "apply job requires a request rationale"})
        if not 1 <= self.chunk_size <= MAX_LEGACY_APPLY_CHUNK_ROWS:
            raise ValidationError(
                {"chunk_size": f"chunk size must be between 1 and {MAX_LEGACY_APPLY_CHUNK_ROWS}"}
            )
        if self.failure_count > self.max_attempts:
            raise ValidationError({"failure_count": "failure count cannot exceed max attempts"})
        if self.attempt_count != self.claim_generation:
            raise ValidationError(
                {"claim_generation": "claim generation must match the attempt count"}
            )
        if self.status == self.Status.RUNNING:
            if not (
                self.claim_token
                and self.claim_owner
                and self.heartbeat_at is not None
                and self.lease_expires_at is not None
            ):
                raise ValidationError({"status": "running job requires an active claim lease"})
            if self.lease_expires_at <= self.heartbeat_at:
                raise ValidationError(
                    {"lease_expires_at": "running job lease must be in the future"}
                )
        elif any(
            (
                self.claim_token,
                self.claim_owner,
                self.heartbeat_at is not None,
                self.lease_expires_at is not None,
            )
        ):
            raise ValidationError({"status": "only a running job may retain a claim lease"})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        if not self._state.adding:
            current = type(self).objects.filter(pk=self.pk).first()
            if current is None:
                raise PermissionDenied("legacy migration job provenance is immutable")
            immutable_fields = (
                "organization_id",
                "run_id",
                "job_kind",
                "job_sequence",
                "requested_manifest_digest",
                "request_rationale",
                "chunk_size",
                "max_attempts",
                "created_by_id",
            )
            if any(getattr(self, field) != getattr(current, field) for field in immutable_fields):
                raise PermissionDenied("legacy migration job provenance is immutable")
            transitions: dict[str, set[str]] = {
                self.Status.PENDING.value: {
                    self.Status.PENDING.value,
                    self.Status.RUNNING.value,
                    self.Status.FAILED.value,
                    self.Status.CANCELLED.value,
                },
                self.Status.RUNNING.value: {
                    self.Status.RUNNING.value,
                    self.Status.RETRY_WAIT.value,
                    self.Status.COMPLETED.value,
                    self.Status.FAILED.value,
                    self.Status.CANCELLED.value,
                },
                self.Status.RETRY_WAIT.value: {
                    self.Status.RETRY_WAIT.value,
                    self.Status.RUNNING.value,
                    self.Status.FAILED.value,
                    self.Status.CANCELLED.value,
                },
                self.Status.COMPLETED.value: {self.Status.COMPLETED.value},
                self.Status.FAILED.value: {self.Status.FAILED.value},
                self.Status.CANCELLED.value: {self.Status.CANCELLED.value},
            }
            if self.status not in transitions[current.status]:
                raise PermissionDenied("illegal legacy migration job status transition")
            if (
                self.attempt_count < current.attempt_count
                or self.claim_generation < current.claim_generation
                or self.failure_count < current.failure_count
            ):
                raise PermissionDenied("legacy migration job counters cannot decrease")
            if self.status == self.Status.RUNNING and current.status != self.Status.RUNNING:
                if (
                    self.attempt_count != current.attempt_count + 1
                    or self.claim_generation != current.claim_generation + 1
                ):
                    raise PermissionDenied("claim must advance attempt and generation exactly once")
            elif self.status == self.Status.RUNNING and self.claim_token != current.claim_token:
                if (
                    self.attempt_count != current.attempt_count + 1
                    or self.claim_generation != current.claim_generation + 1
                ):
                    raise PermissionDenied(
                        "takeover must advance attempt and generation exactly once"
                    )
            elif (
                self.attempt_count != current.attempt_count
                or self.claim_generation != current.claim_generation
            ):
                raise PermissionDenied("only a claim may advance attempt and generation")
            if self.failure_count > current.failure_count + 1:
                raise PermissionDenied("one settlement may record at most one failure")
            terminal = {
                self.Status.COMPLETED,
                self.Status.FAILED,
                self.Status.CANCELLED,
            }
            if current.status in terminal:
                operational_fields = (
                    "status",
                    "available_at",
                    "claim_token",
                    "claim_owner",
                    "heartbeat_at",
                    "lease_expires_at",
                    "claim_generation",
                    "attempt_count",
                    "failure_count",
                    "next_checkpoint_sequence",
                    "last_error_code",
                    "last_error_message",
                    "started_at",
                    "completed_at",
                )
                if any(
                    getattr(self, field) != getattr(current, field) for field in operational_fields
                ):
                    raise PermissionDenied("terminal legacy migration job evidence is immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("legacy migration jobs cannot be deleted")


class LegacyMigrationCheckpoint(models.Model):
    """A source-range chunk with frozen provenance and service-owned progress."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMMITTED = "committed", "Committed"
        FAILED = "failed", "Failed"

    checkpoint_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization,
        on_delete=models.PROTECT,
        related_name="legacy_migration_checkpoints",
    )
    run = models.ForeignKey(
        LegacyMigrationRun, on_delete=models.PROTECT, related_name="checkpoints"
    )
    job = models.ForeignKey(
        LegacyMigrationJob, on_delete=models.PROTECT, related_name="checkpoints"
    )
    worksheet = models.ForeignKey(
        LegacyWorksheetPlan, on_delete=models.PROTECT, related_name="checkpoints"
    )
    table_plan = models.ForeignKey(
        LegacyTablePlan, on_delete=models.PROTECT, related_name="checkpoints"
    )
    sequence = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    first_source_row = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    last_source_row = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    checkpoint_digest = models.CharField(max_length=64, validators=[SHA256_VALIDATOR])
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    ingestion_run = models.OneToOneField(
        IngestionRun,
        on_delete=models.PROTECT,
        related_name="legacy_migration_checkpoint",
        null=True,
        blank=True,
    )
    total_rows = models.PositiveIntegerField(default=0)
    published_rows = models.PositiveIntegerField(default=0)
    quarantined_rows = models.PositiveIntegerField(default=0)
    duplicate_rows = models.PositiveIntegerField(default=0)
    conflict_rows = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = OperationalCheckpointQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("run", "sequence"), name="uniq_legacy_checkpoint_seq"),
            models.UniqueConstraint(
                fields=("run", "table_plan", "first_source_row", "last_source_row"),
                name="uniq_legacy_checkpoint_table_range",
            ),
            models.CheckConstraint(
                condition=models.Q(last_source_row__gte=models.F("first_source_row")),
                name="legacy_checkpoint_bounds",
            ),
        ]
        indexes = [
            models.Index(fields=("run", "status", "sequence"), name="legacy_checkpoint_state_idx")
        ]

    def clean(self) -> None:
        super().clean()
        if self.run_id and self.run.organization_id != self.organization_id:
            raise ValidationError({"run": "run organization must match checkpoint organization"})
        if self.job_id and (
            self.job.run_id != self.run_id or self.job.organization_id != self.organization_id
        ):
            raise ValidationError({"job": "job must belong to the checkpoint run and organization"})
        if self.worksheet_id and (
            self.worksheet.run_id != self.run_id
            or self.worksheet.organization_id != self.organization_id
        ):
            raise ValidationError(
                {"worksheet": "worksheet must belong to the checkpoint run and organization"}
            )
        if self.table_plan_id:
            if (
                self.table_plan.run_id != self.run_id
                or self.table_plan.organization_id != self.organization_id
                or self.table_plan.worksheet_id != self.worksheet_id
            ):
                raise ValidationError(
                    {"table_plan": "table plan must belong to the checkpoint worksheet and run"}
                )
            if not (
                self.table_plan.start_row
                <= self.first_source_row
                <= self.last_source_row
                <= self.table_plan.end_row
            ):
                raise ValidationError(
                    {"last_source_row": "checkpoint rows must be inside the table region"}
                )
        ingestion_run = self.ingestion_run
        if ingestion_run is not None:
            if ingestion_run.organization_id != self.organization_id:
                raise ValidationError(
                    {
                        "ingestion_run": (
                            "ingestion run organization must match checkpoint organization"
                        )
                    }
                )
            if ingestion_run.artifact_id != self.run.inventory.artifact_id:
                raise ValidationError(
                    {"ingestion_run": "checkpoint ingestion must use the source inventory artifact"}
                )
            if ingestion_run.mapping_template.organization_id != self.organization_id:
                raise ValidationError(
                    {
                        "ingestion_run": "checkpoint mapping must belong to the checkpoint organization"
                    }
                )
            if ingestion_run.source_sheet_name != self.worksheet.sheet_name:
                raise ValidationError(
                    {"ingestion_run": "checkpoint source sheet must match its worksheet"}
                )
            partition_prefix = f"legacy:{self.run_id}:{self.sequence}:"
            if not ingestion_run.source_partition_key.startswith(partition_prefix):
                raise ValidationError(
                    {"ingestion_run": "checkpoint ingestion partition identity is invalid"}
                )
        if self.last_source_row < self.first_source_row:
            raise ValidationError(
                {"last_source_row": "last source row must be at or after first source row"}
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        if not self._state.adding:
            current = type(self).objects.filter(pk=self.pk).first()
            if current is None:
                raise PermissionDenied("legacy migration checkpoint evidence is immutable")
            immutable_fields = (
                "organization_id",
                "run_id",
                "job_id",
                "worksheet_id",
                "table_plan_id",
                "sequence",
                "first_source_row",
                "last_source_row",
                "checkpoint_digest",
            )
            if any(getattr(self, field) != getattr(current, field) for field in immutable_fields):
                raise PermissionDenied("legacy migration checkpoint evidence is immutable")
            operational_fields = (
                "status",
                "ingestion_run_id",
                "total_rows",
                "published_rows",
                "quarantined_rows",
                "duplicate_rows",
                "conflict_rows",
                "completed_at",
            )
            if current.status == self.Status.COMMITTED and any(
                getattr(self, field) != getattr(current, field) for field in operational_fields
            ):
                raise PermissionDenied("committed checkpoint evidence is immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("legacy migration checkpoint evidence is immutable")


class LegacyMigrationDecisionRevision(ImmutableEvidenceModel):
    """Append-only reviewer authorization or withdrawal decision."""

    class Decision(models.TextChoices):
        APPROVE = "approve", "Approve"
        WITHDRAW = "withdraw", "Withdraw"

    evidence_label = "legacy migration decision revision is append-only"

    decision_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization,
        on_delete=models.PROTECT,
        related_name="legacy_migration_decisions",
    )
    run = models.ForeignKey(
        LegacyMigrationRun, on_delete=models.PROTECT, related_name="decision_revisions"
    )
    sequence = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    decision = models.CharField(max_length=16, choices=Decision.choices)
    manifest_digest = models.CharField(max_length=64, validators=[SHA256_VALIDATOR])
    predecessor = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        related_name="successor",
        null=True,
        blank=True,
    )
    actor = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="legacy_migration_decisions"
    )
    rationale = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableEvidenceQuerySet.as_manager()

    class Meta(ImmutableEvidenceModel.Meta):
        ordering = ("sequence", "decision_id")
        constraints = [
            models.UniqueConstraint(fields=("run", "sequence"), name="uniq_legacy_decision_seq")
        ]
        indexes = [
            models.Index(
                fields=("organization", "decision", "created_at"),
                name="legacy_decision_idx",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.run_id and self.run.organization_id != self.organization_id:
            raise ValidationError({"run": "run organization must match decision organization"})
        if self.sequence == 1 and self.predecessor_id is not None:
            raise ValidationError({"predecessor": "the first decision cannot have a predecessor"})
        if self.sequence > 1:
            predecessor = self.predecessor
            if predecessor is None:
                raise ValidationError({"predecessor": "later decisions require a predecessor"})
            if (
                predecessor.run_id != self.run_id
                or predecessor.organization_id != self.organization_id
                or predecessor.sequence + 1 != self.sequence
            ):
                raise ValidationError(
                    {"predecessor": "decision predecessors must be contiguous in the same run"}
                )


class LegacyMigrationManifest(ImmutableEvidenceModel):
    """Immutable digest and payload for dry-run, reconciliation, or withdrawal evidence."""

    class Kind(models.TextChoices):
        DRY_RUN = "dry_run", "Dry run"
        RECONCILIATION = "reconciliation", "Reconciliation"
        WITHDRAWAL = "withdrawal", "Withdrawal"

    evidence_label = "legacy migration manifest"

    manifest_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization,
        on_delete=models.PROTECT,
        related_name="legacy_migration_manifests",
    )
    run = models.ForeignKey(LegacyMigrationRun, on_delete=models.PROTECT, related_name="manifests")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    sequence = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    digest = models.CharField(max_length=64, validators=[SHA256_VALIDATOR])
    payload = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="created_legacy_migration_manifests",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableEvidenceQuerySet.as_manager()

    class Meta(ImmutableEvidenceModel.Meta):
        ordering = ("kind", "sequence", "manifest_id")
        constraints = [
            models.UniqueConstraint(
                fields=("run", "kind", "sequence"), name="uniq_legacy_manifest_seq"
            )
        ]
        indexes = [
            models.Index(
                fields=("organization", "kind", "created_at"),
                name="legacy_manifest_kind_idx",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.run_id and self.run.organization_id != self.organization_id:
            raise ValidationError({"run": "run organization must match manifest organization"})
