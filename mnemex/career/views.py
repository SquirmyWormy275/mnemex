from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from mnemex.accounts.authorization import Action, may_perform, organizations_for_action
from mnemex.accounts.decorators import privileged_session_required
from mnemex.accounts.models import Account
from mnemex.career.forms import IdentityResolutionForm
from mnemex.career.models import CareerAssertionRevision
from mnemex.career.services import reconcile_identity
from mnemex.consent.models import ConsentGrant
from mnemex.foundation.services import IdempotencyConflict
from mnemex.results.models import ReconciliationCase

View = TypeVar("View", bound=Callable[..., HttpResponse])


def identity_reviewer_required(view: View) -> View:
    @privileged_session_required
    @wraps(view)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        actor = cast(Account, request.user)
        if not organizations_for_action(actor, Action.REVIEW_IDENTITY).exists():
            raise PermissionDenied("an MFA-bound identity reviewer role is required")
        return view(request, *args, **kwargs)

    return cast(View, wrapped)


def _add_service_error(form: IdentityResolutionForm, error: Exception) -> None:
    messages = error.messages if isinstance(error, ValidationError) else [str(error)]
    for message in messages:
        form.add_error(None, message)


@identity_reviewer_required
def identity_queue(request: HttpRequest) -> HttpResponse:
    organizations = organizations_for_action(cast(Account, request.user), Action.REVIEW_IDENTITY)
    scoped_cases = ReconciliationCase.objects.filter(
        case_type=ReconciliationCase.CaseType.IDENTITY_UNRESOLVED,
        existing_published_result__organization__in=organizations,
    ).select_related("existing_published_result__organization")
    cases = scoped_cases.filter(
        status=ReconciliationCase.Status.OPEN,
    ).order_by("opened_at")
    resolved_cases = scoped_cases.filter(status=ReconciliationCase.Status.RESOLVED).order_by(
        "-resolved_at"
    )
    return render(
        request,
        "career/identity_queue.html",
        {"cases": cases, "resolved_cases": resolved_cases},
    )


@identity_reviewer_required
def identity_detail(request: HttpRequest, case_id: str) -> HttpResponse:
    case = get_object_or_404(
        ReconciliationCase.objects.select_related("existing_published_result__organization"),
        pk=case_id,
    )
    source = case.existing_published_result
    if source is None:
        raise PermissionDenied("identity case has no published source result")
    actor = cast(Account, request.user)
    if not may_perform(actor, Action.REVIEW_IDENTITY, organization=source.organization):
        raise PermissionDenied("identity case is outside the assigned organization scope")
    form = IdentityResolutionForm(request.POST or None)
    outcome = None
    if request.method == "POST" and form.is_valid():
        consent_grant_id = form.cleaned_data["consent_grant_id"]
        consent_grant = (
            ConsentGrant.objects.filter(pk=consent_grant_id).first()
            if consent_grant_id is not None
            else None
        )
        try:
            outcome = reconcile_identity(
                actor=actor,
                organization=source.organization,
                reconciliation_case=case,
                person=form.cleaned_data["person"],
                authorization_basis_type=form.cleaned_data["authorization_basis_type"],
                authorization_basis_reference=form.cleaned_data["authorization_basis_reference"],
                authorization_captured_at=form.cleaned_data["authorization_captured_at"],
                operator_key=form.cleaned_data["operator_key"],
                consent_grant=consent_grant,
            )
        except (IdempotencyConflict, ValidationError) as error:
            _add_service_error(form, error)
        else:
            target = redirect("career:identity-detail", case_id=case.pk)
            target["Location"] = f"{target.url}?confirmed=1"
            if outcome.replayed:
                target["Location"] += "&replayed=1"
            return target
    assertion = (
        CareerAssertionRevision.objects.filter(reconciliation_case=case)
        .order_by("-revision")
        .first()
    )
    return render(
        request,
        "career/identity_detail.html",
        {
            "case": case,
            "source": source,
            "payload": source.normalized_payload,
            "form": form,
            "assertion": assertion,
            "confirmed": request.GET.get("confirmed") == "1",
            "replayed": request.GET.get("replayed") == "1",
        },
    )
