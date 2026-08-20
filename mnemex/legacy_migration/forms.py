from __future__ import annotations

import json
from typing import Any, cast

from django import forms

from mnemex.accounts.authorization import Action, organizations_for_action
from mnemex.accounts.models import Account
from mnemex.legacy_migration.inspection import MAX_LEGACY_FILE_BYTES
from mnemex.partners.models import PartnerOrganization


class LegacyUploadForm(forms.Form):
    organization = forms.ModelChoiceField(queryset=PartnerOrganization.objects.none())
    source_key = forms.CharField(
        max_length=200,
        help_text="A stable private label for this source collection, such as synthetic-2026.",
    )
    data_rights_reference = forms.CharField(
        max_length=240,
        label="Data-rights reference",
        help_text="Record the authorization or custody reference; do not paste credentials.",
    )
    spreadsheet = forms.FileField(
        help_text="XLSX only, up to 20 MiB. The original stays in private artifact storage.",
        widget=forms.ClearableFileInput(attrs={"accept": ".xlsx"}),
    )

    def __init__(self, *args: Any, actor: Account | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        organization_field = cast(forms.ModelChoiceField, self.fields["organization"])
        organization_field.queryset = (
            organizations_for_action(actor, Action.MANAGE_RESULTS)
            if actor is not None
            else PartnerOrganization.objects.none()
        )

    def clean_source_key(self) -> str:
        value = str(self.cleaned_data["source_key"]).strip()
        if not value:
            raise forms.ValidationError("Enter a stable source key.")
        return value

    def clean_data_rights_reference(self) -> str:
        value = str(self.cleaned_data["data_rights_reference"]).strip()
        if not value:
            raise forms.ValidationError("Enter the data-rights or custody reference.")
        return value

    def clean_spreadsheet(self) -> object:
        uploaded = self.cleaned_data["spreadsheet"]
        if not str(uploaded.name).lower().endswith(".xlsx"):
            raise forms.ValidationError("Upload an XLSX workbook.")
        if uploaded.size < 1 or uploaded.size > MAX_LEGACY_FILE_BYTES:
            raise forms.ValidationError("Workbook must contain 1 byte to 20 MiB.")
        return uploaded


class LegacyConfigurationForm(forms.Form):
    configuration = forms.CharField(
        label="Sheet and table configuration",
        widget=forms.Textarea(attrs={"rows": 30, "spellcheck": "false", "class": "code-input"}),
        help_text=(
            "JSON list: include every sheet exactly once. Included sheets need one or more "
            "rectangular table regions; ignored sheets need an ignore_reason."
        ),
    )

    def clean_configuration(self) -> list[dict[str, object]]:
        raw = self.cleaned_data["configuration"]
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise forms.ValidationError(
                f"Configuration is not valid JSON near line {error.lineno}, column {error.colno}."
            ) from error
        if not isinstance(value, list) or not value:
            raise forms.ValidationError("Configuration must be a non-empty JSON list.")
        if not all(isinstance(item, dict) for item in value):
            raise forms.ValidationError("Every sheet configuration must be a JSON object.")
        return cast(list[dict[str, object]], value)


class LegacyDecisionForm(forms.Form):
    manifest_digest = forms.RegexField(
        regex=r"^[0-9a-f]{64}$",
        max_length=64,
        label="Exact manifest digest",
        widget=forms.TextInput(attrs={"class": "mono", "autocomplete": "off"}),
    )
    rationale = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Required. This becomes append-only reviewer evidence.",
    )


class LegacyApplyForm(forms.Form):
    manifest_digest = forms.RegexField(
        regex=r"^[0-9a-f]{64}$",
        max_length=64,
        label="Approved dry-run manifest digest",
        widget=forms.TextInput(attrs={"class": "mono", "autocomplete": "off"}),
    )
    rationale = forms.CharField(
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text=(
            "Required. This becomes immutable manager evidence for this apply or recovery request."
        ),
    )
