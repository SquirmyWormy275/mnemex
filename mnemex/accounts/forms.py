from __future__ import annotations

import secrets
import time
from typing import TYPE_CHECKING, Any

from allauth.mfa import app_settings
from allauth.mfa.base.forms import AuthenticateForm, ReauthenticateForm
from allauth.mfa.base.internal.flows import check_rate_limit
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import format_hotp_value, hotp_value
from allauth.mfa.utils import decrypt
from django import forms
from django.conf import settings
from django.core.cache import caches
from django.db import transaction

from mnemex.accounts.authorization import Action, organizations_for_action
from mnemex.accounts.models import (
    Account,
    PrivilegedRecoveryRequest,
    PrivilegedRoleAssignment,
)
from mnemex.partners.models import PartnerOrganization


def _matching_totp_counter(authenticator: Authenticator, code: str) -> int | None:
    bypass = app_settings.TOTP_INSECURE_BYPASS_CODE
    if bypass and secrets.compare_digest(code, bypass):
        return -1
    secret = decrypt(authenticator.data["secret"])
    current = int(time.time()) // app_settings.TOTP_PERIOD
    for offset in range(-app_settings.TOTP_TOLERANCE, app_settings.TOTP_TOLERANCE + 1):
        counter = current + offset
        expected = format_hotp_value(hotp_value(secret, counter))
        if secrets.compare_digest(code, expected):
            return counter
    return None


def _claim_totp_once(authenticator: Authenticator, code: str) -> bool:
    counter = _matching_totp_counter(authenticator, code)
    if counter is None:
        return False
    if counter == -1:
        return True
    key = f"mnemex.mfa.totp.claim:user={authenticator.user_id}:auth={authenticator.pk}:counter={counter}"
    ttl = app_settings.TOTP_PERIOD * (2 * app_settings.TOTP_TOLERANCE + 2)
    try:
        security_cache = caches[settings.MNEMEX_SECURITY_CACHE_ALIAS]
        claimed = security_cache.add(key, "claimed", timeout=ttl)
    except Exception:
        # This is an authorization decision. A shared-cache outage or malformed
        # backend response must deny the code; falling back to process-local
        # state would permit the same TOTP on another web process.
        return False
    return claimed is True


def _validate_recovery_code(authenticator: Authenticator, code: str) -> Authenticator | None:
    with transaction.atomic():
        locked = Authenticator.objects.select_for_update().get(pk=authenticator.pk)
        if locked.wrap().validate_code(code):
            return locked
    return None


class _AtomicCodeValidationMixin:
    user: Any
    authenticator: Authenticator
    if TYPE_CHECKING:
        cleaned_data: dict[str, Any]

        def _emit_authentication_failed(self, authenticator: Authenticator) -> None: ...

    def clean_code(self) -> str:
        clear_rate_limit = check_rate_limit(self.user)
        code = self.cleaned_data["code"]
        authenticators = list(
            Authenticator.objects.filter(user=self.user)
            .exclude(type=Authenticator.Type.WEBAUTHN)
            .order_by("type", "pk")
        )
        main = next(
            (item for item in authenticators if item.type == Authenticator.Type.TOTP),
            authenticators[0] if authenticators else None,
        )
        for authenticator in authenticators:
            accepted: Authenticator | None = None
            if authenticator.type == Authenticator.Type.TOTP:
                if _claim_totp_once(authenticator, code):
                    accepted = authenticator
            elif authenticator.type == Authenticator.Type.RECOVERY_CODES:
                accepted = _validate_recovery_code(authenticator, code)
            if accepted is not None:
                accepted.user = self.user
                self.authenticator = accepted
                clear_rate_limit()
                return code
        if main is not None:
            self._emit_authentication_failed(main)
        from allauth.mfa.adapter import get_adapter

        raise get_adapter().validation_error("incorrect_code")


class MnemexAuthenticateForm(_AtomicCodeValidationMixin, AuthenticateForm):
    pass


class MnemexReauthenticateForm(_AtomicCodeValidationMixin, ReauthenticateForm):
    pass


class PrivilegedInvitationAcceptanceForm(forms.Form):
    secret = forms.CharField(
        label="One-time invitation code",
        max_length=160,
        strip=True,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                "autocomplete": "one-time-code",
                "spellcheck": "false",
            },
        ),
    )


class PrivilegedRecoveryApprovalForm(forms.Form):
    external_evidence_reference = forms.CharField(
        label="External evidence reference",
        max_length=120,
        help_text="Enter the reference from the independent verification record.",
        widget=forms.TextInput(attrs={"autocomplete": "off", "spellcheck": "false"}),
    )


class PrivilegedRecoveryRestorationForm(forms.Form):
    confirm_reenrollment = forms.BooleanField(
        label="I confirmed a new authenticator is enrolled before restoring access."
    )


class SecurityInvitationInitiationForm(forms.Form):
    subject_account_id = forms.UUIDField(
        label="Account ID",
        help_text="Use the opaque account ID from the independently verified staff record.",
    )
    role = forms.ChoiceField(label="Access role", choices=PrivilegedRoleAssignment.Role.choices)
    scope = forms.ChoiceField(label="Scope", choices=PrivilegedRoleAssignment.Scope.choices)
    organization = forms.ModelChoiceField(
        label="Partner organization",
        queryset=PartnerOrganization.objects.none(),
        required=False,
        empty_label="Not used for platform-wide access",
    )
    external_evidence_reference = forms.CharField(
        label="External evidence reference",
        max_length=120,
        widget=forms.TextInput(attrs={"autocomplete": "off", "spellcheck": "false"}),
    )

    def __init__(self, *args: Any, requested_by: Account, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        organization_field = self.fields["organization"]
        assert isinstance(organization_field, forms.ModelChoiceField)
        organization_field.queryset = organizations_for_action(
            requested_by,
            Action.MANAGE_SECURITY_OPERATIONS,
        )


class SecurityRecoveryInitiationForm(forms.Form):
    subject_account_id = forms.UUIDField(
        label="Account ID",
        help_text="Use the opaque account ID from the independently verified staff record.",
    )
    external_evidence_reference = forms.CharField(
        label="External evidence reference",
        max_length=120,
        widget=forms.TextInput(attrs={"autocomplete": "off", "spellcheck": "false"}),
    )
    reason_code = forms.ChoiceField(
        label="Reason",
        choices=PrivilegedRecoveryRequest.Reason.choices,
    )
