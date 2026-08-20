from __future__ import annotations

from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Any, cast

from django import forms
from django.core import signing
from django.utils import timezone

from mnemex.accounts.authorization import Action, organizations_for_action
from mnemex.accounts.models import Account
from mnemex.export.models import ExportEligibilityRevision
from mnemex.partners.models import PartnerOrganization


class ExportReviewForm(forms.Form):
    decision = forms.ChoiceField(
        choices=ExportEligibilityRevision.Decision.choices,
        widget=forms.RadioSelect,
    )
    reason = forms.CharField(max_length=240, widget=forms.Textarea(attrs={"rows": 3}))
    operator_key = forms.CharField(
        max_length=200,
        help_text="A unique key makes an exact retry safe.",
    )


class EvidenceSnapshotForm(forms.Form):
    CAPTURE_TOKEN_MAX_AGE_SECONDS = 15 * 60
    CAPTURE_TOKEN_SALT = "mnemex.export.snapshot-capture.v1"

    organization = forms.ModelChoiceField(queryset=PartnerOrganization.objects.none())
    source_id = forms.CharField(
        max_length=128,
        help_text="A namespaced immutable identifier, for example mnemex:snapshot:show-2026-v1.",
    )
    cutoff = forms.DateField(
        help_text="Exclusive UTC date: results on this date are not included.",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    capture_token = forms.CharField(widget=forms.HiddenInput)
    operator_key = forms.CharField(
        max_length=200,
        help_text="A unique key makes an exact retry safe.",
    )

    def __init__(self, *args: Any, actor: Account, **kwargs: Any) -> None:
        initial = dict(kwargs.pop("initial", {}) or {})
        capture_time = timezone.now().astimezone(dt_timezone.utc)
        initial.setdefault(
            "capture_token",
            signing.dumps(
                {
                    "actor_id": str(actor.pk),
                    "captured_at": capture_time.isoformat(),
                },
                salt=self.CAPTURE_TOKEN_SALT,
                compress=True,
            ),
        )
        kwargs["initial"] = initial
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.capture_time = capture_time
        organization_field = cast(forms.ModelChoiceField, self.fields["organization"])
        organization_field.queryset = organizations_for_action(actor, Action.REVIEW_EXPORT)

    def clean_capture_token(self) -> str:
        token = cast(str, self.cleaned_data["capture_token"])
        try:
            payload = signing.loads(
                token,
                salt=self.CAPTURE_TOKEN_SALT,
                max_age=self.CAPTURE_TOKEN_MAX_AGE_SECONDS,
            )
        except (signing.BadSignature, signing.SignatureExpired) as exc:
            raise forms.ValidationError("Capture token is invalid or expired.") from exc
        if not isinstance(payload, dict) or payload.get("actor_id") != str(self.actor.pk):
            raise forms.ValidationError("Capture token belongs to a different operator.")
        try:
            captured_at = datetime.fromisoformat(str(payload["captured_at"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise forms.ValidationError("Capture token is invalid or expired.") from exc
        if captured_at.tzinfo is None:
            raise forms.ValidationError("Capture token is invalid or expired.")
        self.capture_time = captured_at.astimezone(dt_timezone.utc)
        return token

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean() or {}
        if "capture_token" in cleaned_data:
            cleaned_data["captured_at"] = self.capture_time
        return cleaned_data
