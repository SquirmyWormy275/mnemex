from __future__ import annotations

import csv
import hashlib
import json
from functools import wraps
from io import StringIO
from typing import Any, Callable, TypeVar, cast

from django.core.exceptions import (
    ImproperlyConfigured,
    PermissionDenied,
    ValidationError,
)
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from mnemex.accounts.authorization import Action, may_perform, organizations_for_action
from mnemex.accounts.decorators import privileged_session_required
from mnemex.accounts.models import Account
from mnemex.legacy_migration.forms import (
    LegacyApplyForm,
    LegacyConfigurationForm,
    LegacyDecisionForm,
    LegacyUploadForm,
)
from mnemex.legacy_migration.inspection import (
    LegacyWorkbookInspection,
    inspect_legacy_workbook,
)
from mnemex.legacy_migration.jobs import enqueue_apply_job
from mnemex.legacy_migration.models import (
    MAX_LEGACY_APPLY_CHUNK_ROWS,
    LegacyMigrationJob,
    LegacyMigrationManifest,
    LegacyMigrationRun,
    LegacySourceInventory,
)
from mnemex.legacy_migration.private_workbooks import (
    PrivateWorkbookUnavailable,
    read_private_workbook,
)
from mnemex.legacy_migration.services import (
    approve_migration,
    configure_migration_run,
    dry_run_migration,
    withdraw_migration,
)
from mnemex.partners.models import PartnerOrganization
from mnemex.results.artifact_lifecycle import (
    abandon_artifact_write,
    complete_artifact_write,
    install_registered_artifact,
    lock_artifact_write,
)
from mnemex.results.artifacts import (
    ArtifactCollisionError,
    private_artifact_store_from_settings,
)
from mnemex.results.models import SourceArtifact

View = TypeVar("View", bound=Callable[..., HttpResponse])
_PARSER_VERSION = "legacy-xlsx-inspector-v1"
_RULESET_VERSION = "legacy-mapping-v1"


def _workspace_required(view: View) -> View:
    @privileged_session_required
    @wraps(view)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        actor = cast(Account, request.user)
        if not (
            organizations_for_action(actor, Action.MANAGE_RESULTS).exists()
            or organizations_for_action(actor, Action.REVIEW_EXPORT).exists()
        ):
            raise PermissionDenied("an MFA-bound legacy migration role is required")
        return view(request, *args, **kwargs)

    return cast(View, wrapped)


def _manager_required(view: View) -> View:
    @privileged_session_required
    @wraps(view)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        actor = cast(Account, request.user)
        if not organizations_for_action(actor, Action.MANAGE_RESULTS).exists():
            raise PermissionDenied("an MFA-bound results manager role is required")
        return view(request, *args, **kwargs)

    return cast(View, wrapped)


def _reviewer_required(view: View) -> View:
    @privileged_session_required
    @wraps(view)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        actor = cast(Account, request.user)
        if not organizations_for_action(actor, Action.REVIEW_EXPORT).exists():
            raise PermissionDenied("an MFA-bound export reviewer role is required")
        return view(request, *args, **kwargs)

    return cast(View, wrapped)


def _run_queryset() -> QuerySet[LegacyMigrationRun]:
    return LegacyMigrationRun.objects.select_related(
        "organization", "inventory", "inventory__artifact"
    ).prefetch_related(
        "worksheets__table_plans",
        "decision_revisions",
        Prefetch(
            "jobs",
            queryset=LegacyMigrationJob.objects.order_by("job_sequence", "created_at", "job_id"),
            to_attr="ordered_jobs",
        ),
        "checkpoints",
        "manifests",
    )


def _run(run_id: str) -> LegacyMigrationRun:
    return get_object_or_404(_run_queryset(), pk=run_id)


def _scoped_run(actor: Account, run_id: str, *actions: Action) -> LegacyMigrationRun:
    organization_ids: set[object] = set()
    for action in actions:
        organization_ids.update(
            organizations_for_action(actor, action).values_list("organization_id", flat=True)
        )
    return get_object_or_404(
        _run_queryset(),
        pk=run_id,
        organization_id__in=organization_ids,
    )


def _manager_run(actor: Account, run_id: str) -> LegacyMigrationRun:
    return _scoped_run(actor, run_id, Action.MANAGE_RESULTS)


def _reviewer_run(actor: Account, run_id: str) -> LegacyMigrationRun:
    return _scoped_run(actor, run_id, Action.REVIEW_EXPORT)


def _read_workbook(run: LegacyMigrationRun) -> bytes:
    return read_private_workbook(run)


def _form_error(form: Any, error: Exception) -> None:
    if isinstance(error, ValidationError):
        messages = error.messages
    elif isinstance(error, ImproperlyConfigured):
        messages = ["Private artifact storage is not configured for this environment."]
    elif isinstance(error, ArtifactCollisionError):
        messages = ["The private artifact digest address contains unexpected content."]
    else:
        messages = ["The migration operation could not be completed safely."]
    for message in messages:
        form.add_error(None, message)


def _inventory_digest(
    *,
    organization: PartnerOrganization,
    source_key: str,
    rights: str,
    artifact_digest: str,
) -> str:
    payload = {
        "version": "legacy-source-inventory-v1",
        "organization_id": str(organization.pk),
        "source_namespace": "legacy-results",
        "source_key": source_key,
        "data_rights_reference": rights,
        "parser_version": _PARSER_VERSION,
        "artifact_digest": artifact_digest,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


@_workspace_required
def dashboard(request: HttpRequest) -> HttpResponse:
    actor = cast(Account, request.user)
    managed_ids = set(
        organizations_for_action(actor, Action.MANAGE_RESULTS).values_list(
            "organization_id", flat=True
        )
    )
    reviewed_ids = set(
        organizations_for_action(actor, Action.REVIEW_EXPORT).values_list(
            "organization_id", flat=True
        )
    )
    organization_ids = managed_ids | reviewed_ids
    runs = (
        LegacyMigrationRun.objects.filter(organization_id__in=organization_ids)
        .select_related("organization")
        .prefetch_related(
            Prefetch(
                "jobs",
                queryset=LegacyMigrationJob.objects.order_by(
                    "job_sequence", "created_at", "job_id"
                ),
                to_attr="ordered_jobs",
            )
        )
        .order_by("-created_at")[:50]
    )
    return render(
        request,
        "legacy_migration/dashboard.html",
        {
            "runs": runs,
            "dashboard_rows": [{"run": run, "job_rows": _job_rows(run)} for run in runs],
            "can_upload": bool(managed_ids),
            "managed_ids": managed_ids,
            "reviewed_ids": reviewed_ids,
        },
    )


@_manager_required
def upload(request: HttpRequest) -> HttpResponse:
    actor = cast(Account, request.user)
    form = LegacyUploadForm(request.POST or None, request.FILES or None, actor=actor)
    if request.method == "POST" and form.is_valid():
        organization = cast(PartnerOrganization, form.cleaned_data["organization"])
        uploaded = form.cleaned_data["spreadsheet"]
        content = uploaded.read()
        source_key = str(form.cleaned_data["source_key"])
        rights = str(form.cleaned_data["data_rights_reference"])
        attempt = None
        try:
            inspection = inspect_legacy_workbook(content)
            store = private_artifact_store_from_settings()
            attempt = install_registered_artifact(
                store=store,
                organization=organization,
                content=content,
                filename=uploaded.name,
            )
            object_reference = attempt.artifact_object.object_reference
            with transaction.atomic():
                attempt = lock_artifact_write(attempt)
                artifact, _ = SourceArtifact.objects.get_or_create(
                    organization=organization,
                    kind=SourceArtifact.Kind.SPREADSHEET,
                    digest=inspection.artifact_digest,
                    defaults={
                        "original_name": uploaded.name,
                        "content_type": uploaded.content_type
                        or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "byte_size": len(content),
                        "object_reference": object_reference,
                        "uploaded_by": actor,
                        "retention_class": "legacy-results-source-pilot",
                    },
                )
                if hasattr(artifact, "legacy_source_inventory"):
                    raise ValidationError("this private workbook is already inventoried")
                inventory = LegacySourceInventory.objects.create(
                    organization=organization,
                    artifact=artifact,
                    source_namespace="legacy-results",
                    source_key=source_key,
                    data_rights_reference=rights,
                    parser_version=_PARSER_VERSION,
                    manifest_digest=_inventory_digest(
                        organization=organization,
                        source_key=source_key,
                        rights=rights,
                        artifact_digest=inspection.artifact_digest,
                    ),
                    created_by=actor,
                )
                run = LegacyMigrationRun.objects.create(
                    organization=organization,
                    inventory=inventory,
                    run_version=1,
                    ruleset_version=_RULESET_VERSION,
                    created_by=actor,
                )
                complete_artifact_write(attempt=attempt, artifact=artifact)
        except (
            ArtifactCollisionError,
            ImproperlyConfigured,
            IntegrityError,
            ValidationError,
        ) as error:
            if attempt is not None:
                if isinstance(error, ArtifactCollisionError):
                    error_code = "artifact_collision"
                elif isinstance(error, IntegrityError):
                    error_code = "database_transaction_failed"
                else:
                    error_code = "upload_validation_failed"
                abandon_artifact_write(attempt=attempt, error_code=error_code)
            _form_error(form, error)
        except Exception:
            if attempt is not None:
                abandon_artifact_write(attempt=attempt, error_code="upload_failed")
            raise
        else:
            return redirect("legacy_migration:run-detail", run_id=run.pk)
    return render(request, "legacy_migration/upload.html", {"form": form})


def _default_configuration(inspection: LegacyWorkbookInspection) -> str:
    configuration = [
        {
            "sheet_name": sheet.name,
            "disposition": "ignored",
            "ignore_reason": "Replace with a specific evidence-based reason, or include tables.",
            "tables": [],
        }
        for sheet in inspection.sheets
    ]
    return json.dumps(configuration, indent=2)


@_manager_required
def configure(request: HttpRequest, run_id: str) -> HttpResponse:
    actor = cast(Account, request.user)
    run = _manager_run(actor, run_id)
    try:
        content = _read_workbook(run)
        inspection = inspect_legacy_workbook(content)
    except (ImproperlyConfigured, PrivateWorkbookUnavailable, ValidationError) as error:
        form = LegacyConfigurationForm(request.POST or None)
        _form_error(form, error)
        return render(
            request,
            "legacy_migration/configure.html",
            {"run": run, "form": form, "inspection": None},
        )
    initial = {"configuration": _default_configuration(inspection)}
    form = LegacyConfigurationForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            configure_migration_run(
                actor=actor,
                run=run,
                workbook_content=content,
                sheet_configurations=form.cleaned_data["configuration"],
            )
        except ValidationError as error:
            _form_error(form, error)
        else:
            return redirect("legacy_migration:run-detail", run_id=run.pk)
    return render(
        request,
        "legacy_migration/configure.html",
        {"run": run, "form": form, "inspection": inspection},
    )


def _preview_rows(run: LegacyMigrationRun) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for preview in run.row_previews.select_related("table_plan").order_by(
        "source_sheet_index", "source_row_number", "source_column_start"
    )[:250]:
        codes = [
            str(error.get("code", "unknown"))
            for error in preview.validation_errors
            if isinstance(error, dict)
        ]
        rows.append({"preview": preview, "reason_codes": codes})
    return rows


def _job_rows(run: LegacyMigrationRun) -> list[dict[str, object]]:
    now = timezone.now()
    rows: list[dict[str, object]] = []
    labels: dict[str, str] = {
        LegacyMigrationJob.Status.PENDING: "Queued",
        LegacyMigrationJob.Status.RUNNING: "Running",
        LegacyMigrationJob.Status.RETRY_WAIT: "Retry scheduled",
        LegacyMigrationJob.Status.COMPLETED: "Completed",
        LegacyMigrationJob.Status.FAILED: "Failed",
        LegacyMigrationJob.Status.CANCELLED: "Cancelled",
    }
    guidance: dict[str, str] = {
        LegacyMigrationJob.Status.PENDING: "Waiting for an authorized worker.",
        LegacyMigrationJob.Status.RUNNING: "No operator action is required while heartbeat is current.",
        LegacyMigrationJob.Status.RETRY_WAIT: "A bounded automatic retry is scheduled.",
        LegacyMigrationJob.Status.COMPLETED: "No recovery action is required.",
        LegacyMigrationJob.Status.FAILED: "Authorized operator review is required before a new request.",
        LegacyMigrationJob.Status.CANCELLED: "No work will run for this cancelled request.",
    }
    jobs = getattr(run, "ordered_jobs", None)
    if jobs is None:
        jobs = run.jobs.order_by("job_sequence", "created_at", "job_id")
    for job in jobs:
        stale = bool(
            job.status == LegacyMigrationJob.Status.RUNNING
            and job.lease_expires_at is not None
            and job.lease_expires_at <= now
        )
        rows.append(
            {
                "job": job,
                "status_label": labels[job.status],
                "is_stale": stale,
                "next_retry": (
                    job.available_at if job.status == LegacyMigrationJob.Status.RETRY_WAIT else None
                ),
                "guidance": (
                    "Worker heartbeat is stale; another worker may reclaim the lease."
                    if stale
                    else guidance[job.status]
                ),
            }
        )
    return rows


def _detail_response(
    request: HttpRequest,
    run: LegacyMigrationRun,
    *,
    approval_form: LegacyDecisionForm | None = None,
    apply_form: LegacyApplyForm | None = None,
    withdrawal_form: LegacyDecisionForm | None = None,
    dry_run_error: str = "",
) -> HttpResponse:
    actor = cast(Account, request.user)
    can_manage = may_perform(actor, Action.MANAGE_RESULTS, organization=run.organization)
    can_review = may_perform(actor, Action.REVIEW_EXPORT, organization=run.organization)
    inspection: LegacyWorkbookInspection | None = None
    storage_error = ""
    if run.state == LegacyMigrationRun.State.DISCOVERED:
        try:
            inspection = inspect_legacy_workbook(_read_workbook(run))
        except (ImproperlyConfigured, PrivateWorkbookUnavailable, ValidationError):
            storage_error = "Private workbook content is unavailable or failed integrity checks."
    reconciliation = run.manifests.filter(kind=LegacyMigrationManifest.Kind.RECONCILIATION).first()
    authority_digest = reconciliation.digest if reconciliation else run.dry_run_manifest_digest
    action_errors: list[str] = []
    for form in (approval_form, apply_form, withdrawal_form):
        if form is not None and form.is_bound:
            action_errors.extend(str(message) for message in form.non_field_errors())
    return render(
        request,
        "legacy_migration/detail.html",
        {
            "run": run,
            "inspection": inspection,
            "storage_error": storage_error,
            "dry_run_error": dry_run_error,
            "action_errors": action_errors,
            "can_manage": can_manage,
            "can_review": can_review,
            "preview_rows": _preview_rows(run),
            "job_rows": _job_rows(run),
            "approval_form": approval_form
            or LegacyDecisionForm(initial={"manifest_digest": run.dry_run_manifest_digest}),
            "apply_form": apply_form
            or LegacyApplyForm(initial={"manifest_digest": run.dry_run_manifest_digest}),
            "withdrawal_form": withdrawal_form
            or LegacyDecisionForm(initial={"manifest_digest": authority_digest}),
            "reconciliation": reconciliation,
        },
    )


@_workspace_required
def run_detail(request: HttpRequest, run_id: str) -> HttpResponse:
    run = _scoped_run(
        cast(Account, request.user),
        run_id,
        Action.MANAGE_RESULTS,
        Action.REVIEW_EXPORT,
    )
    return _detail_response(request, run)


@_manager_required
def dry_run(request: HttpRequest, run_id: str) -> HttpResponse:
    actor = cast(Account, request.user)
    run = _manager_run(actor, run_id)
    if request.method != "POST":
        return redirect("legacy_migration:run-detail", run_id=run.pk)
    try:
        content = _read_workbook(run)
        dry_run_migration(actor=actor, run=run, workbook_content=content)
    except (ImproperlyConfigured, PrivateWorkbookUnavailable, ValidationError) as error:
        if isinstance(error, ValidationError):
            message = " ".join(error.messages)
        elif isinstance(error, PrivateWorkbookUnavailable):
            message = "Private workbook content is unavailable."
        else:
            message = "Private artifact storage is not configured for this environment."
        return _detail_response(request, _run(run_id), dry_run_error=message)
    return redirect("legacy_migration:run-detail", run_id=run.pk)


@_reviewer_required
def approve(request: HttpRequest, run_id: str) -> HttpResponse:
    actor = cast(Account, request.user)
    run = _reviewer_run(actor, run_id)
    if request.method != "POST":
        return redirect("legacy_migration:run-detail", run_id=run.pk)
    form = LegacyDecisionForm(request.POST)
    if form.is_valid():
        try:
            approve_migration(
                actor=actor,
                run=run,
                manifest_digest=str(form.cleaned_data["manifest_digest"]),
                rationale=str(form.cleaned_data["rationale"]),
            )
        except ValidationError as error:
            _form_error(form, error)
        else:
            return redirect("legacy_migration:run-detail", run_id=run.pk)
    return _detail_response(request, _run(run_id), approval_form=form)


@_manager_required
def apply(request: HttpRequest, run_id: str) -> HttpResponse:
    actor = cast(Account, request.user)
    run = _manager_run(actor, run_id)
    if request.method != "POST":
        return redirect("legacy_migration:run-detail", run_id=run.pk)
    form = LegacyApplyForm(request.POST)
    if form.is_valid():
        try:
            enqueue_apply_job(
                actor=actor,
                run=run,
                approved_manifest_digest=str(form.cleaned_data["manifest_digest"]),
                chunk_size=MAX_LEGACY_APPLY_CHUNK_ROWS,
                request_rationale=str(form.cleaned_data["rationale"]),
            )
        except ValidationError as error:
            _form_error(form, error)
        else:
            return redirect("legacy_migration:run-detail", run_id=run.pk)
    return _detail_response(request, _run(run_id), apply_form=form)


@_workspace_required
def report_csv(request: HttpRequest, run_id: str) -> HttpResponse:
    run = _scoped_run(
        cast(Account, request.user),
        run_id,
        Action.MANAGE_RESULTS,
        Action.REVIEW_EXPORT,
    )
    manifest = run.manifests.filter(kind=LegacyMigrationManifest.Kind.RECONCILIATION).first()
    if manifest is None:
        raise ValidationError("reconciliation is available only after a completed apply")
    previews = {str(item.pk): item for item in run.row_previews.all()}
    output = StringIO(newline="")
    fields = (
        "sheet_index",
        "table_plan_id",
        "source_row_number",
        "payload_digest",
        "dry_run_classification",
        "apply_outcome",
        "diverged",
        "reason_codes",
        "checkpoint_sequence",
    )
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\r\n")
    writer.writeheader()
    for evidence in manifest.payload.get("rows", []):
        if not isinstance(evidence, dict):
            continue
        preview = previews.get(str(evidence.get("preview_id", "")))
        reason_codes = []
        if preview is not None:
            reason_codes = [
                str(item.get("code", "unknown"))
                for item in preview.validation_errors
                if isinstance(item, dict)
            ]
        writer.writerow(
            {
                "sheet_index": evidence.get("sheet_index", ""),
                "table_plan_id": evidence.get("table_plan_id", ""),
                "source_row_number": evidence.get("source_row_number", ""),
                "payload_digest": evidence.get("payload_digest", ""),
                "dry_run_classification": evidence.get("dry_run_classification", ""),
                "apply_outcome": evidence.get("apply_outcome", ""),
                "diverged": evidence.get("diverged", ""),
                "reason_codes": "|".join(reason_codes),
                "checkpoint_sequence": evidence.get("checkpoint_sequence", ""),
            }
        )
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="legacy-reconciliation-{run.pk}.csv"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


@_reviewer_required
def withdraw(request: HttpRequest, run_id: str) -> HttpResponse:
    actor = cast(Account, request.user)
    run = _reviewer_run(actor, run_id)
    if request.method != "POST":
        return redirect("legacy_migration:run-detail", run_id=run.pk)
    form = LegacyDecisionForm(request.POST)
    if form.is_valid():
        try:
            withdraw_migration(
                actor=actor,
                run=run,
                manifest_digest=str(form.cleaned_data["manifest_digest"]),
                rationale=str(form.cleaned_data["rationale"]),
            )
        except ValidationError as error:
            _form_error(form, error)
        else:
            return redirect("legacy_migration:run-detail", run_id=run.pk)
    return _detail_response(request, _run(run_id), withdrawal_form=form)
