from __future__ import annotations

from uuid import UUID

from allauth.mfa.models import Authenticator
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from mnemex.accounts.action_assurance import claim_action_ticket, issue_action_ticket
from mnemex.accounts.assurance import current_request_account, has_fresh_mfa_session
from mnemex.accounts.authorization import Action, has_effective_role, organizations_for_action
from mnemex.accounts.forms import (
    MnemexReauthenticateForm,
    PrivilegedInvitationAcceptanceForm,
    PrivilegedRecoveryApprovalForm,
    PrivilegedRecoveryRestorationForm,
    SecurityInvitationInitiationForm,
    SecurityRecoveryInitiationForm,
)
from mnemex.accounts.models import Account, PrivilegedInvitation, PrivilegedRoleAssignment
from mnemex.accounts.services import (
    accept_privileged_invitation,
    approve_privileged_recovery,
    create_privileged_invitation,
    create_privileged_recovery,
    restore_recovered_privileges,
    visible_invitations_for,
    visible_recoveries_for,
)


def _eligible_for_privileged_step_up(request: HttpRequest) -> bool:
    account = current_request_account(request)
    return bool(
        getattr(settings, "MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED", False)
        and account is not None
        and account.is_active
        and account.email_verified_at is not None
        and account.privileged_roles.filter(revoked_at__isnull=True).exists()
        and Authenticator.objects.filter(
            user=account,
            type=Authenticator.Type.TOTP,
        ).exists()
    )


@login_required
@require_POST
def action_step_up(request: HttpRequest) -> JsonResponse:
    """Verify MFA in place and issue a route-bound one-use action ticket."""

    if not _eligible_for_privileged_step_up(request):
        return JsonResponse({"code": "verification_unavailable"}, status=403)
    account = current_request_account(request)
    assert account is not None
    target_path = request.POST.get("target_path", "")
    target_method = request.POST.get("target_method", "")

    if not has_fresh_mfa_session(
        request,
        account,
        max_age_seconds=getattr(settings, "MNEMEX_SENSITIVE_MFA_MAX_AGE_SECONDS", 300),
    ):
        code = request.POST.get("code", "")
        if not code:
            return JsonResponse({"code": "mfa_required"}, status=428)
        form = MnemexReauthenticateForm(user=account, data={"code": code})
        if not form.is_valid():
            return JsonResponse({"code": "verification_failed"}, status=400)
        form.save()

    try:
        ticket = issue_action_ticket(
            request,
            target_path=target_path,
            target_method=target_method,
        )
    except Exception:
        return JsonResponse({"code": "verification_unavailable"}, status=403)
    return JsonResponse({"code": "action_ready", "ticket": ticket})


def _security_account(request: HttpRequest) -> Account | None:
    account = current_request_account(request)
    if account is None:
        return None
    has_platform_scope = has_effective_role(
        account, PrivilegedRoleAssignment.Role.SECURITY_ADMINISTRATOR
    )
    has_tenant_scope = organizations_for_action(account, Action.MANAGE_SECURITY_OPERATIONS).exists()
    if not has_platform_scope and not has_tenant_scope:
        return None
    return account


def _require_fresh_security_session(
    request: HttpRequest,
    account: Account,
) -> HttpResponse | None:
    if request.method == "POST" and getattr(
        settings,
        "MNEMEX_PRIVILEGED_ACTION_TICKETS_REQUIRED",
        False,
    ):
        claim_action_ticket(
            request,
            token=request.headers.get("X-MNEMEX-Action-Ticket", ""),
        )
        return None
    if has_fresh_mfa_session(
        request,
        account,
        max_age_seconds=settings.MNEMEX_SENSITIVE_MFA_MAX_AGE_SECONDS,
    ):
        return None
    return redirect(f"{reverse('mfa_reauthenticate')}?next={request.get_full_path()}")


@login_required
def invitation_accept(request: HttpRequest, request_id: UUID) -> HttpResponse:
    account = current_request_account(request)
    assert account is not None
    invitation = (
        PrivilegedInvitation.objects.select_related("operation_state", "organization")
        .filter(pk=request_id, subject=account)
        .first()
    )
    if invitation is None:
        raise Http404("Security operation not found")
    if not has_fresh_mfa_session(
        request,
        account,
        max_age_seconds=settings.MNEMEX_SENSITIVE_MFA_MAX_AGE_SECONDS,
    ):
        return redirect(f"{reverse('mfa_reauthenticate')}?next={request.get_full_path()}")
    form = PrivilegedInvitationAcceptanceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            accept_privileged_invitation(
                subject=account,
                request_id=invitation.pk,
                secret=form.cleaned_data["secret"],
            )
        except ValidationError:
            form.add_error(None, "This invitation could not be accepted.")
        else:
            messages.success(request, "Access invitation accepted.")
            return redirect("mfa_index")
    return render(
        request,
        "accounts/security_operations/invitation_accept.html",
        {"invitation": invitation, "form": form},
        status=400 if request.method == "POST" and form.errors else 200,
    )


@login_required
def security_operations(request: HttpRequest) -> HttpResponse:
    account = _security_account(request)
    if account is None:
        raise PermissionDenied("security administrator access is required")
    assurance_response = _require_fresh_security_session(request, account)
    if assurance_response is not None:
        return assurance_response
    invitation_form = SecurityInvitationInitiationForm(
        requested_by=account,
        auto_id="id_invitation_%s",
    )
    recovery_form = SecurityRecoveryInitiationForm(auto_id="id_recovery_%s")
    initiation_error = False
    invitation_secret = None
    created_invitation = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_invitation":
            submitted = SecurityInvitationInitiationForm(
                request.POST,
                requested_by=account,
                auto_id="id_invitation_%s",
            )
            if submitted.is_valid():
                subject = Account.objects.filter(
                    pk=submitted.cleaned_data["subject_account_id"]
                ).first()
                if subject is not None:
                    try:
                        created_invitation, invitation_secret = create_privileged_invitation(
                            requested_by=account,
                            subject=subject,
                            role=submitted.cleaned_data["role"],
                            scope=submitted.cleaned_data["scope"],
                            organization=submitted.cleaned_data["organization"],
                            external_evidence_reference=submitted.cleaned_data[
                                "external_evidence_reference"
                            ],
                        )
                    except (PermissionDenied, ValidationError):
                        initiation_error = True
                else:
                    initiation_error = True
            else:
                initiation_error = True
        elif action == "create_recovery":
            submitted_recovery = SecurityRecoveryInitiationForm(
                request.POST,
                auto_id="id_recovery_%s",
            )
            if submitted_recovery.is_valid():
                subject = Account.objects.filter(
                    pk=submitted_recovery.cleaned_data["subject_account_id"]
                ).first()
                if subject is not None:
                    try:
                        recovery = create_privileged_recovery(
                            requested_by=account,
                            subject=subject,
                            external_evidence_reference=submitted_recovery.cleaned_data[
                                "external_evidence_reference"
                            ],
                            reason_code=submitted_recovery.cleaned_data["reason_code"],
                        )
                    except (PermissionDenied, ValidationError):
                        initiation_error = True
                    else:
                        return redirect(
                            "accounts:security-operation-detail",
                            request_id=recovery.pk,
                        )
                else:
                    initiation_error = True
            else:
                initiation_error = True
        else:
            initiation_error = True
    recoveries = visible_recoveries_for(account).select_related(
        "operation_state",
        "approval",
    )[:100]
    invitations = visible_invitations_for(account).select_related(
        "operation_state",
        "organization",
    )[:100]
    response = render(
        request,
        "accounts/security_operations/queue.html",
        {
            "recoveries": recoveries,
            "invitations": invitations,
            "invitation_form": invitation_form,
            "recovery_form": recovery_form,
            "initiation_error": initiation_error,
            "invitation_secret": invitation_secret,
            "created_invitation": created_invitation,
        },
        status=400 if initiation_error else 200,
    )
    if invitation_secret is not None:
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-MNEMEX-One-Time-Result"] = "invitation-secret-v1"
    return response


@login_required
def security_operation_detail(request: HttpRequest, request_id: UUID) -> HttpResponse:
    account = current_request_account(request)
    assert account is not None
    recovery = (
        visible_recoveries_for(account)
        .select_related("operation_state", "approval")
        .filter(pk=request_id)
        .first()
    )
    if recovery is None:
        raise Http404("Security operation not found")
    assurance_response = _require_fresh_security_session(request, account)
    if assurance_response is not None:
        return assurance_response
    approval_form = PrivilegedRecoveryApprovalForm(
        request.POST if request.POST.get("action") == "approve" else None
    )
    restoration_form = PrivilegedRecoveryRestorationForm(
        request.POST if request.POST.get("action") == "restore" else None
    )
    if request.method == "POST":
        try:
            if request.POST.get("action") == "approve" and approval_form.is_valid():
                approve_privileged_recovery(
                    recovery=recovery,
                    approved_by=account,
                    external_evidence_reference=approval_form.cleaned_data[
                        "external_evidence_reference"
                    ],
                )
                messages.success(request, "Recovery approved. Access remains suspended.")
                return redirect("accounts:security-operation-detail", request_id=recovery.pk)
            if request.POST.get("action") == "restore" and restoration_form.is_valid():
                restore_recovered_privileges(recovery=recovery, restored_by=account)
                messages.success(request, "Privileges restored after MFA re-enrollment.")
                return redirect("accounts:security-operation-detail", request_id=recovery.pk)
        except (PermissionDenied, ValidationError):
            if request.POST.get("action") == "approve":
                approval_form.add_error(None, "Recovery could not be approved.")
            else:
                restoration_form.add_error(None, "Access could not be restored.")
    return render(
        request,
        "accounts/security_operations/detail.html",
        {
            "recovery": recovery,
            "approval_form": approval_form,
            "restoration_form": restoration_form,
        },
        status=400 if request.method == "POST" else 200,
    )
