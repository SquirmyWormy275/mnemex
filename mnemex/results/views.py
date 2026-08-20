from __future__ import annotations

import csv
from functools import wraps
from io import StringIO
from typing import Any, Callable, TypeVar, cast

from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from mnemex.accounts.authorization import (
    Action,
    has_effective_role,
    may_perform,
    organizations_for_action,
)
from mnemex.accounts.decorators import privileged_session_required
from mnemex.accounts.models import Account, PrivilegedRoleAssignment
from mnemex.foundation.services import IdempotencyConflict
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
from mnemex.results.forms import (
    ManualBatchForm,
    ManualResultFormSet,
    MappingTemplateForm,
    SpreadsheetUploadForm,
)
from mnemex.results.models import (
    IngestionRun,
    MappingTemplate,
    ReconciliationCase,
    StagedResult,
)
from mnemex.results.services import ingest_manual_rows, ingest_spreadsheet_bytes

View = TypeVar("View", bound=Callable[..., HttpResponse])

_CANONICAL_INTAKE_FIELDS = (
    "source_result_id",
    "source_revision",
    "source_event_id",
    "event_name",
    "result_date",
    "competitor_name",
    "discipline",
    "score_type",
    "score",
    "heat_id",
    "wood_species",
    "wood_diameter_mm",
    "wood_quality",
)
_CANONICAL_FIELD_MAP = {field: field for field in _CANONICAL_INTAKE_FIELDS}
_STANDARD_MAPPING_NAME = "MNEMEX standard columns"


def results_manager_required(view: View) -> View:
    @privileged_session_required
    @wraps(view)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        actor = cast(Account, request.user)
        if not (
            has_effective_role(actor, PrivilegedRoleAssignment.Role.RESULTS_MANAGER)
            or organizations_for_action(actor, Action.MANAGE_RESULTS).exists()
        ):
            raise PermissionDenied("an MFA-bound results manager role is required")
        return view(request, *args, **kwargs)

    return cast(View, wrapped)


def reviewer_workspace_required(view: View) -> View:
    @privileged_session_required
    @wraps(view)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        actor = cast(Account, request.user)
        roles_and_actions = (
            (PrivilegedRoleAssignment.Role.RESULTS_MANAGER, Action.MANAGE_RESULTS),
            (PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER, Action.REVIEW_IDENTITY),
            (PrivilegedRoleAssignment.Role.EXPORT_REVIEWER, Action.REVIEW_EXPORT),
        )
        if not any(
            has_effective_role(actor, role) or organizations_for_action(actor, action).exists()
            for role, action in roles_and_actions
        ):
            raise PermissionDenied("an MFA-bound Results Desk role is required")
        return view(request, *args, **kwargs)

    return cast(View, wrapped)


@reviewer_workspace_required
def dashboard(request: HttpRequest) -> HttpResponse:
    actor = cast(Account, request.user)
    accessible_organizations = organizations_for_action(actor, Action.MANAGE_RESULTS)
    identity_organizations = organizations_for_action(actor, Action.REVIEW_IDENTITY)
    export_organizations = organizations_for_action(actor, Action.REVIEW_EXPORT)
    can_manage_results = (
        has_effective_role(actor, PrivilegedRoleAssignment.Role.RESULTS_MANAGER)
        or accessible_organizations.exists()
    )
    can_review_identity = (
        has_effective_role(actor, PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER)
        or identity_organizations.exists()
    )
    can_review_export = (
        has_effective_role(actor, PrivilegedRoleAssignment.Role.EXPORT_REVIEWER)
        or export_organizations.exists()
    )
    recent_runs = (
        IngestionRun.objects.filter(organization__in=accessible_organizations)
        .select_related("organization")
        .order_by("-created_at")[:8]
    )
    context = {
        "can_manage_results": can_manage_results,
        "can_review_identity": can_review_identity,
        "can_review_export": can_review_export,
        "recent_runs": recent_runs,
        "run_count": IngestionRun.objects.filter(organization__in=accessible_organizations).count(),
        "published_count": sum(run.published_rows for run in recent_runs),
        "open_case_count": ReconciliationCase.objects.filter(
            status=ReconciliationCase.Status.OPEN,
            staged_result__run__organization__in=accessible_organizations,
        ).count(),
        "mapping_count": MappingTemplate.objects.filter(
            is_active=True, organization__in=accessible_organizations
        ).count(),
        "identity_case_count": ReconciliationCase.objects.filter(
            case_type=ReconciliationCase.CaseType.IDENTITY_UNRESOLVED,
            status=ReconciliationCase.Status.OPEN,
            existing_published_result__organization__in=identity_organizations,
        ).count(),
    }
    return render(request, "results/dashboard.html", context)


@results_manager_required
def starter_csv(request: HttpRequest) -> HttpResponse:
    """Return a tenant-neutral canonical CSV with one conspicuously synthetic row."""

    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=_CANONICAL_INTAKE_FIELDS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerow(
        {
            "source_result_id": "synthetic-result-001",
            "source_revision": "1",
            "source_event_id": "synthetic-event-2026",
            "event_name": "Synthetic Demo Show - Replace",
            "result_date": "2026-01-15",
            "competitor_name": "Synthetic Competitor - Replace",
            "discipline": "UNDERHAND",
            "score_type": "time",
            "score": "12.34",
            "heat_id": "synthetic-heat-1",
            "wood_species": "Pine",
            "wood_diameter_mm": "325",
            "wood_quality": "8",
        }
    )
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="mnemex-results-starter.csv"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _enforce_posted_scope(request: HttpRequest) -> None:
    """Reject an existing out-of-scope tenant before a form can mask it as invalid."""

    organization_id = request.POST.get("organization")
    if not organization_id:
        return
    try:
        organization = PartnerOrganization.objects.filter(pk=organization_id).first()
    except (TypeError, ValueError, ValidationError):
        return
    if organization is not None and not may_perform(
        cast(Account, request.user), Action.MANAGE_RESULTS, organization=organization
    ):
        raise PermissionDenied("results operation is outside the assigned organization scope")
    mapping_template_id = request.POST.get("mapping_template")
    if not mapping_template_id:
        return
    try:
        mapping_template = (
            MappingTemplate.objects.select_related("organization")
            .filter(pk=mapping_template_id)
            .first()
        )
    except (TypeError, ValueError, ValidationError):
        return
    if mapping_template is not None and not may_perform(
        cast(Account, request.user),
        Action.MANAGE_RESULTS,
        organization=mapping_template.organization,
    ):
        raise PermissionDenied("mapping template is outside the assigned organization scope")


@results_manager_required
def mapping_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        _enforce_posted_scope(request)
    form = MappingTemplateForm(request.POST or None, actor=cast(Account, request.user))
    if request.method == "POST" and form.is_valid():
        organization = cast(PartnerOrganization, form.cleaned_data["organization"])
        name = str(form.cleaned_data["name"]).strip()
        latest = (
            MappingTemplate.objects.filter(organization=organization, name=name).aggregate(
                latest=Max("version")
            )["latest"]
            or 0
        )
        MappingTemplate.objects.create(
            organization=organization,
            name=name,
            version=latest + 1,
            field_map=form.field_map(),
            created_by=cast(Account, request.user),
        )
        return redirect("results:dashboard")
    return render(request, "results/mapping_form.html", {"form": form})


def _add_service_error(form: Any, error: Exception) -> None:
    if isinstance(error, ValidationError):
        messages = error.messages
    else:
        messages = [str(error)]
    for message in messages:
        form.add_error(None, message)


def _standard_mapping(organization: PartnerOrganization, actor: Account) -> MappingTemplate:
    """Return one active canonical mapping, serializing creation per organization."""

    with transaction.atomic():
        locked_organization = PartnerOrganization.objects.select_for_update().get(
            pk=organization.pk
        )
        candidates = MappingTemplate.objects.filter(
            organization=locked_organization,
            name=_STANDARD_MAPPING_NAME,
            is_active=True,
        ).order_by("-version")
        for mapping in candidates:
            if mapping.field_map == _CANONICAL_FIELD_MAP:
                return mapping
        latest = (
            MappingTemplate.objects.filter(
                organization=locked_organization, name=_STANDARD_MAPPING_NAME
            ).aggregate(latest=Max("version"))["latest"]
            or 0
        )
        return MappingTemplate.objects.create(
            organization=locked_organization,
            name=_STANDARD_MAPPING_NAME,
            version=latest + 1,
            field_map=_CANONICAL_FIELD_MAP,
            created_by=actor,
        )


@results_manager_required
def upload(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        _enforce_posted_scope(request)
    form = SpreadsheetUploadForm(
        request.POST or None,
        request.FILES or None,
        actor=cast(Account, request.user),
    )
    if request.method == "POST" and form.is_valid():
        actor = cast(Account, request.user)
        organization = cast(PartnerOrganization, form.cleaned_data["organization"])
        if not may_perform(actor, Action.MANAGE_RESULTS, organization=organization):
            raise PermissionDenied("results operation is outside the assigned organization scope")
        selected_mapping = form.cleaned_data["mapping_template"]
        mapping = (
            cast(MappingTemplate, selected_mapping)
            if selected_mapping is not None
            else _standard_mapping(organization, actor)
        )
        uploaded = form.cleaned_data["spreadsheet"]
        content = uploaded.read()
        attempt = None
        try:
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
                outcome = ingest_spreadsheet_bytes(
                    actor=actor,
                    organization=organization,
                    mapping_template=mapping,
                    operator_key=str(form.cleaned_data["operator_key"]),
                    filename=uploaded.name,
                    content_type=uploaded.content_type or "application/octet-stream",
                    content=content,
                    object_reference=object_reference,
                    worksheet_name=str(form.cleaned_data["worksheet_name"] or ""),
                )
                complete_artifact_write(
                    attempt=attempt,
                    artifact=outcome.run.artifact,
                )
        except Exception as error:
            if attempt is not None:
                if isinstance(error, IdempotencyConflict):
                    error_code = "idempotency_conflict"
                elif isinstance(error, ArtifactCollisionError):
                    error_code = "artifact_collision"
                elif isinstance(error, (ImproperlyConfigured, ValidationError)):
                    error_code = "upload_validation_failed"
                else:
                    error_code = "upload_failed"
                abandon_artifact_write(attempt=attempt, error_code=error_code)
            if isinstance(
                error,
                (
                    ArtifactCollisionError,
                    IdempotencyConflict,
                    ImproperlyConfigured,
                    ValidationError,
                ),
            ):
                _add_service_error(form, error)
            else:
                raise
        else:
            target = redirect("results:run-detail", run_id=outcome.run.pk)
            if outcome.replayed:
                target["Location"] = f"{target.url}?replayed=1"
            return target
    return render(request, "results/upload_form.html", {"form": form})


_MANUAL_FIELD_MAP = _CANONICAL_FIELD_MAP


def _manual_mapping(organization: PartnerOrganization, actor: Account) -> MappingTemplate:
    mapping = MappingTemplate.objects.filter(
        organization=organization,
        name="MNEMEX canonical manual entry",
        field_map=_MANUAL_FIELD_MAP,
        is_active=True,
    ).first()
    if mapping is not None:
        return mapping
    latest = (
        MappingTemplate.objects.filter(
            organization=organization, name="MNEMEX canonical manual entry"
        ).aggregate(latest=Max("version"))["latest"]
        or 0
    )
    return MappingTemplate.objects.create(
        organization=organization,
        name="MNEMEX canonical manual entry",
        version=latest + 1,
        field_map=_MANUAL_FIELD_MAP,
        created_by=actor,
    )


@results_manager_required
def manual(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        _enforce_posted_scope(request)
    batch_form = ManualBatchForm(request.POST or None, actor=cast(Account, request.user))
    row_formset = ManualResultFormSet(request.POST or None, prefix="rows")
    if request.method == "POST" and batch_form.is_valid() and row_formset.is_valid():
        actor = cast(Account, request.user)
        organization = cast(PartnerOrganization, batch_form.cleaned_data["organization"])
        rows = [form.cleaned_data for form in row_formset.forms if form.cleaned_data]
        mapping = _manual_mapping(organization, actor)
        try:
            outcome = ingest_manual_rows(
                actor=actor,
                organization=organization,
                mapping_template=mapping,
                operator_key=str(batch_form.cleaned_data["operator_key"]),
                rows=rows,
            )
        except (IdempotencyConflict, ValidationError) as error:
            _add_service_error(batch_form, error)
        else:
            target = redirect("results:run-detail", run_id=outcome.run.pk)
            if outcome.replayed:
                target["Location"] = f"{target.url}?replayed=1"
            return target
    return render(
        request,
        "results/manual_form.html",
        {"batch_form": batch_form, "row_formset": row_formset},
    )


@results_manager_required
def run_detail(request: HttpRequest, run_id: str) -> HttpResponse:
    run = get_object_or_404(
        IngestionRun.objects.select_related("organization", "artifact", "mapping_template"),
        pk=run_id,
    )
    if not may_perform(
        cast(Account, request.user), Action.MANAGE_RESULTS, organization=run.organization
    ):
        raise PermissionDenied("ingestion run is outside the assigned organization scope")
    rows = run.staged_results.order_by("row_number")
    return render(
        request,
        "results/run_detail.html",
        {
            "run": run,
            "rows": rows,
            "replayed": request.GET.get("replayed") == "1",
            "has_issues": bool(run.quarantined_rows or run.conflict_rows),
        },
    )


def _validation_reasons(row: StagedResult) -> str:
    if row.outcome == StagedResult.Outcome.CONFLICT:
        return (
            "source_result_id:source_payload_conflict: Submitted content differs from the "
            "published source revision."
        )
    reasons = []
    for error in sorted(
        row.validation_errors,
        key=lambda item: (
            str(item.get("field", "")),
            str(item.get("code", "")),
            str(item.get("message", "")),
        ),
    ):
        reasons.append(
            f"{error.get('field', '')}:{error.get('code', '')}: {error.get('message', '')}"
        )
    return " | ".join(reasons)


@results_manager_required
def run_issues_csv(request: HttpRequest, run_id: str) -> HttpResponse:
    run = get_object_or_404(IngestionRun.objects.select_related("organization"), pk=run_id)
    if not may_perform(
        cast(Account, request.user), Action.MANAGE_RESULTS, organization=run.organization
    ):
        raise PermissionDenied("ingestion run is outside the assigned organization scope")

    fieldnames = [
        *_CANONICAL_INTAKE_FIELDS,
        "outcome",
        "validation_reasons",
        "source_sheet",
        "source_row",
        "operator_guidance",
    ]
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\r\n")
    writer.writeheader()
    issue_rows = run.staged_results.filter(
        outcome__in=(StagedResult.Outcome.QUARANTINED, StagedResult.Outcome.CONFLICT)
    ).order_by("row_number")
    guidance = (
        "Changed content requires a new operator key. An approved correction also requires "
        "the next source revision; do not mutate this run."
    )
    for row in issue_rows:
        payload = row.normalized_payload if isinstance(row.normalized_payload, dict) else {}
        writer.writerow(
            {
                **{field: payload.get(field, "") for field in _CANONICAL_INTAKE_FIELDS},
                "outcome": row.outcome,
                "validation_reasons": _validation_reasons(row),
                "source_sheet": row.source_sheet_name,
                "source_row": row.source_row_number or "",
                "operator_guidance": guidance,
            }
        )
    response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="mnemex-run-{run.run_id}-issues.csv"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
