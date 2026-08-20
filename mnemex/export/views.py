from __future__ import annotations

import csv
import json
from functools import wraps
from typing import Any, Callable, TypeVar, cast
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import OuterRef, QuerySet, Subquery
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from mnemex.accounts.authorization import Action, may_perform, organizations_for_action
from mnemex.accounts.decorators import privileged_session_required
from mnemex.accounts.models import Account
from mnemex.career.models import CareerAssertionRevision
from mnemex.export.forms import EvidenceSnapshotForm, ExportReviewForm
from mnemex.export.models import EvidenceSnapshotManifest, ExportEligibilityRevision
from mnemex.export.services import generate_evidence_snapshot, review_export_eligibility
from mnemex.foundation.services import IdempotencyConflict
from mnemex.partners.models import PartnerOrganization
from mnemex.results.models import PublishedSourceResult

View = TypeVar("View", bound=Callable[..., HttpResponse])
REVIEW_PAGE_SIZE = 100
EXCLUSION_PAGE_SIZE = 100
MAX_EXCLUSION_DOWNLOAD_ROWS = 100_000
_EXCLUSION_REASONS = {
    "after_capture",
    "invalid_diameter",
    "invalid_quality",
    "invalid_result_date",
    "invalid_score",
    "invalid_source_payload",
    "invalid_species",
    "missing_result_date",
    "missing_source_event_id",
    "missing_wood_metadata",
    "on_or_after_cutoff",
    "review_rejected",
    "superseded_identity_assertion",
    "superseded_source_revision",
    "unreviewed",
    "unsupported_discipline",
    "unsupported_score_type",
}


def export_reviewer_required(view: View) -> View:
    @privileged_session_required
    @wraps(view)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        actor = cast(Account, request.user)
        if not organizations_for_action(actor, Action.REVIEW_EXPORT).exists():
            raise PermissionDenied("an MFA-bound export reviewer role is required")
        return view(request, *args, **kwargs)

    return cast(View, wrapped)


def _add_service_error(form: Any, error: Exception) -> None:
    messages = error.messages if isinstance(error, ValidationError) else [str(error)]
    for message in messages:
        form.add_error(None, message)


def _current_assertions(
    organizations: QuerySet[PartnerOrganization],
) -> QuerySet[CareerAssertionRevision]:
    superseded_identity = CareerAssertionRevision.objects.filter(predecessor__isnull=False).values(
        "predecessor_id"
    )
    superseded_source = PublishedSourceResult.objects.filter(predecessor__isnull=False).values(
        "predecessor_id"
    )
    latest_eligibility = ExportEligibilityRevision.objects.filter(
        career_assertion_id=OuterRef("pk")
    ).order_by("-revision", "-eligibility_revision_id")
    return (
        CareerAssertionRevision.objects.filter(organization__in=organizations)
        .exclude(pk__in=superseded_identity)
        .exclude(source_result_id__in=superseded_source)
        .select_related("organization", "source_result")
        .annotate(portal_eligibility_decision=Subquery(latest_eligibility.values("decision")[:1]))
        .order_by("-created_at")
    )


def _current_eligibility(
    assertion: CareerAssertionRevision,
) -> ExportEligibilityRevision | None:
    return (
        ExportEligibilityRevision.objects.filter(career_assertion=assertion)
        .order_by("-revision")
        .first()
    )


def _eligibility_label(assertion: CareerAssertionRevision) -> str | None:
    decision = getattr(assertion, "portal_eligibility_decision", None)
    if not isinstance(decision, str):
        return None
    return dict(ExportEligibilityRevision.Decision.choices).get(decision)


@export_reviewer_required
def review_queue(request: HttpRequest) -> HttpResponse:
    organizations = organizations_for_action(cast(Account, request.user), Action.REVIEW_EXPORT)
    review_page = Paginator(_current_assertions(organizations), REVIEW_PAGE_SIZE).get_page(
        request.GET.get("page")
    )
    reviews = [
        {
            "assertion": assertion,
            "eligibility_label": _eligibility_label(assertion),
        }
        for assertion in review_page.object_list
    ]
    snapshots = EvidenceSnapshotManifest.objects.filter(organization__in=organizations).order_by(
        "-created_at"
    )[:10]
    return render(
        request,
        "export/review_queue.html",
        {"review_page": review_page, "reviews": reviews, "snapshots": snapshots},
    )


@export_reviewer_required
def review_detail(request: HttpRequest, assertion_id: str) -> HttpResponse:
    assertion = get_object_or_404(
        CareerAssertionRevision.objects.select_related("organization", "source_result"),
        pk=assertion_id,
    )
    actor = cast(Account, request.user)
    if not may_perform(actor, Action.REVIEW_EXPORT, organization=assertion.organization):
        raise PermissionDenied("career assertion is outside the assigned organization scope")
    form = ExportReviewForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            outcome = review_export_eligibility(
                actor=actor,
                organization=assertion.organization,
                career_assertion=assertion,
                decision=form.cleaned_data["decision"],
                reason=form.cleaned_data["reason"],
                operator_key=form.cleaned_data["operator_key"],
            )
        except (IdempotencyConflict, ValidationError) as error:
            _add_service_error(form, error)
        else:
            target = redirect("export:review-detail", assertion_id=assertion.pk)
            target["Location"] = f"{target.url}?confirmed=1"
            if outcome.replayed:
                target["Location"] += "&replayed=1"
            return target
    return render(
        request,
        "export/review_detail.html",
        {
            "assertion": assertion,
            "payload": assertion.source_result.normalized_payload,
            "form": form,
            "eligibility": _current_eligibility(assertion),
            "confirmed": request.GET.get("confirmed") == "1",
            "replayed": request.GET.get("replayed") == "1",
        },
    )


def _enforce_posted_scope(request: HttpRequest) -> None:
    organization_id = request.POST.get("organization")
    if not organization_id:
        return
    try:
        organization = PartnerOrganization.objects.filter(pk=organization_id).first()
    except (TypeError, ValueError, ValidationError):
        return
    if organization is not None and not may_perform(
        cast(Account, request.user), Action.REVIEW_EXPORT, organization=organization
    ):
        raise PermissionDenied("snapshot organization is outside the assigned scope")


@export_reviewer_required
def snapshot_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        _enforce_posted_scope(request)
    actor = cast(Account, request.user)
    form = EvidenceSnapshotForm(request.POST or None, actor=actor)
    if request.method == "POST" and form.is_valid():
        try:
            outcome = generate_evidence_snapshot(
                actor=actor,
                organization=form.cleaned_data["organization"],
                source_id=form.cleaned_data["source_id"],
                cutoff=form.cleaned_data["cutoff"],
                captured_at=form.cleaned_data["captured_at"],
                operator_key=form.cleaned_data["operator_key"],
            )
        except (IdempotencyConflict, ValidationError) as error:
            _add_service_error(form, error)
        else:
            target = redirect("export:snapshot-detail", snapshot_id=outcome.snapshot.pk)
            if outcome.replayed:
                target["Location"] = f"{target.url}?replayed=1"
            return target
    return render(
        request,
        "export/snapshot_form.html",
        {"capture_time": form.capture_time, "form": form},
    )


def _authorized_snapshot(request: HttpRequest, snapshot_id: str) -> EvidenceSnapshotManifest:
    snapshot = get_object_or_404(
        EvidenceSnapshotManifest.objects.select_related("organization"), pk=snapshot_id
    )
    if not may_perform(
        cast(Account, request.user), Action.REVIEW_EXPORT, organization=snapshot.organization
    ):
        raise PermissionDenied("snapshot is outside the assigned organization scope")
    return snapshot


@export_reviewer_required
def snapshot_detail(request: HttpRequest, snapshot_id: str) -> HttpResponse:
    snapshot = _authorized_snapshot(request, snapshot_id)
    exclusions = _safe_exclusions(snapshot)
    exclusion_page = Paginator(exclusions, EXCLUSION_PAGE_SIZE).get_page(
        request.GET.get("exclusions_page")
    )
    return render(
        request,
        "export/snapshot_detail.html",
        {
            "exclusion_page": exclusion_page,
            "replayed": request.GET.get("replayed") == "1",
            "snapshot": snapshot,
        },
    )


@export_reviewer_required
def snapshot_download(request: HttpRequest, snapshot_id: str) -> HttpResponse:
    snapshot = _authorized_snapshot(request, snapshot_id)
    content = json.dumps(
        snapshot.envelope,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    response = HttpResponse(content, content_type="application/json")
    response["Content-Disposition"] = (
        f'attachment; filename="mnemex-evidence-{snapshot.snapshot_id}.json"'
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _safe_exclusions(snapshot: EvidenceSnapshotManifest) -> list[dict[str, str]]:
    if not isinstance(snapshot.exclusions, list):
        return []
    safe: list[dict[str, str]] = []
    for item in snapshot.exclusions[:MAX_EXCLUSION_DOWNLOAD_ROWS]:
        if not isinstance(item, dict):
            continue
        assertion_id = item.get("assertion_revision_id")
        try:
            normalized_id = str(UUID(str(assertion_id)))
        except (TypeError, ValueError, AttributeError):
            normalized_id = "invalid_assertion_revision_id"
        reason = item.get("reason")
        normalized_reason = str(reason) if reason in _EXCLUSION_REASONS else "invalid_reason"
        safe.append(
            {
                "assertion_revision_id": normalized_id,
                "reason": normalized_reason,
            }
        )
    return safe


@export_reviewer_required
def snapshot_exclusions_download(request: HttpRequest, snapshot_id: str) -> HttpResponse:
    snapshot = _authorized_snapshot(request, snapshot_id)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="mnemex-exclusions-{snapshot.snapshot_id}.csv"'
    )
    response["X-Content-Type-Options"] = "nosniff"
    writer = csv.writer(response, lineterminator="\n")
    writer.writerow(("assertion_revision_id", "reason"))
    for exclusion in _safe_exclusions(snapshot):
        writer.writerow((exclusion["assertion_revision_id"], exclusion["reason"]))
    return response
