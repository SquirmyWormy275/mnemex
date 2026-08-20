from __future__ import annotations

from typing import Any, cast

from django import forms
from django.forms import BaseFormSet, formset_factory

from mnemex.accounts.authorization import Action, organizations_for_action
from mnemex.accounts.models import Account
from mnemex.partners.models import PartnerOrganization
from mnemex.results.models import MappingTemplate
from mnemex.results.services import MAX_FILE_BYTES
from mnemex.schema import Discipline, ScoreType


class MappingTemplateForm(forms.Form):
    organization = forms.ModelChoiceField(queryset=PartnerOrganization.objects.none())
    name = forms.CharField(max_length=160, help_text="A recognizable name for this file layout.")
    source_result_id = forms.CharField(max_length=160, label="Source result ID column")
    source_revision = forms.CharField(max_length=160, label="Revision column")
    source_event_id = forms.CharField(max_length=160, label="Source event ID column")
    event_name = forms.CharField(max_length=160, label="Event name column")
    result_date = forms.CharField(
        max_length=160,
        label="Result date column",
        help_text="The source values must use YYYY-MM-DD.",
    )
    competitor_name = forms.CharField(max_length=160, label="Competitor name column")
    discipline = forms.CharField(max_length=160, label="Discipline column")
    score_type = forms.CharField(max_length=160, label="Score type column")
    score = forms.CharField(max_length=160, label="Score column")
    heat_id = forms.CharField(max_length=160, required=False, label="Heat ID column")
    wood_species = forms.CharField(max_length=160, required=False, label="Wood species column")
    wood_diameter_mm = forms.CharField(
        max_length=160, required=False, label="Wood diameter (mm) column"
    )
    wood_quality = forms.CharField(max_length=160, required=False, label="Wood quality column")

    def __init__(self, *args: Any, actor: Account | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        organization_field = cast(forms.ModelChoiceField, self.fields["organization"])
        organization_field.queryset = (
            organizations_for_action(actor, Action.MANAGE_RESULTS)
            if actor is not None
            else PartnerOrganization.objects.none()
        )

    def field_map(self) -> dict[str, str]:
        required = {
            key: str(self.cleaned_data[key]).strip()
            for key in (
                "source_result_id",
                "source_revision",
                "source_event_id",
                "event_name",
                "result_date",
                "competitor_name",
                "discipline",
                "score_type",
                "score",
            )
        }
        optional = {
            key: str(self.cleaned_data[key]).strip()
            for key in ("heat_id", "wood_species", "wood_diameter_mm", "wood_quality")
            if self.cleaned_data.get(key)
        }
        return required | optional


class SpreadsheetUploadForm(forms.Form):
    organization = forms.ModelChoiceField(queryset=PartnerOrganization.objects.none())
    mapping_template = forms.ModelChoiceField(
        queryset=MappingTemplate.objects.none(),
        required=False,
        empty_label="Use MNEMEX standard columns (recommended)",
        label="Column mapping",
        help_text="Leave this on the recommended option when using the MNEMEX starter file.",
    )
    operator_key = forms.CharField(
        max_length=200,
        help_text="Use the same key to safely retry this exact upload.",
    )
    worksheet_name = forms.CharField(
        max_length=128,
        required=False,
        label="XLSX worksheet name",
        help_text=(
            "Optional for a one-sheet workbook. Required when an XLSX workbook has "
            "multiple worksheets. Names must match exactly."
        ),
    )
    spreadsheet = forms.FileField(
        help_text="CSV or XLSX, up to 5 MiB.",
        widget=forms.ClearableFileInput(attrs={"accept": ".csv,.xlsx"}),
    )

    def __init__(self, *args: Any, actor: Account | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        organization_field = cast(forms.ModelChoiceField, self.fields["organization"])
        mapping_field = cast(forms.ModelChoiceField, self.fields["mapping_template"])
        accessible_organizations = (
            organizations_for_action(actor, Action.MANAGE_RESULTS)
            if actor is not None
            else PartnerOrganization.objects.none()
        )
        organization_field.queryset = accessible_organizations
        mapping_field.queryset = MappingTemplate.objects.filter(
            is_active=True,
            organization__in=accessible_organizations,
        ).select_related("organization")

    def clean_spreadsheet(self) -> object:
        uploaded = self.cleaned_data["spreadsheet"]
        if not str(uploaded.name).lower().endswith((".csv", ".xlsx")):
            raise forms.ValidationError("Upload a CSV or XLSX file.")
        if uploaded.size < 1 or uploaded.size > MAX_FILE_BYTES:
            raise forms.ValidationError("Spreadsheet must contain 1 byte to 5 MiB.")
        return uploaded

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        organization = cleaned.get("organization")
        mapping = cleaned.get("mapping_template")
        if organization is not None and mapping is not None:
            if mapping.organization_id != organization.organization_id:
                self.add_error(
                    "mapping_template", "Choose a mapping for the selected organization."
                )
        return cleaned


class ManualBatchForm(forms.Form):
    organization = forms.ModelChoiceField(queryset=PartnerOrganization.objects.none())
    operator_key = forms.CharField(
        max_length=200,
        help_text="Use the same key to safely retry this exact batch.",
    )

    def __init__(self, *args: Any, actor: Account | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        organization_field = cast(forms.ModelChoiceField, self.fields["organization"])
        organization_field.queryset = (
            organizations_for_action(actor, Action.MANAGE_RESULTS)
            if actor is not None
            else PartnerOrganization.objects.none()
        )


class ManualResultRowForm(forms.Form):
    _BROWSER_DEFAULTS = {
        "discipline": next(iter(Discipline)).value,
        "score_type": next(iter(ScoreType)).value,
    }

    source_result_id = forms.CharField(max_length=200, label="Result ID")
    source_revision = forms.IntegerField(min_value=1, label="Revision")
    source_event_id = forms.CharField(max_length=200, label="Event ID")
    event_name = forms.CharField(max_length=240, label="Event name")
    result_date = forms.CharField(
        max_length=10,
        label="Result date",
        help_text="YYYY-MM-DD",
        widget=forms.TextInput(attrs={"type": "date", "placeholder": "YYYY-MM-DD"}),
    )
    competitor_name = forms.CharField(max_length=240, label="Competitor")
    discipline = forms.ChoiceField(choices=[(item.value, item.name) for item in Discipline])
    score_type = forms.ChoiceField(
        choices=[(item.value, item.name.replace("_", " ").title()) for item in ScoreType],
        label="Score type",
    )
    score = forms.CharField(
        max_length=80,
        help_text="A numeric value. Invalid values are quarantined with an explanation.",
    )
    heat_id = forms.CharField(max_length=200, required=False, label="Heat ID")
    wood_species = forms.CharField(max_length=160, required=False, label="Wood species")
    wood_diameter_mm = forms.CharField(
        max_length=80,
        required=False,
        label="Wood diameter (mm)",
        help_text="Optional whole number greater than zero.",
    )
    wood_quality = forms.CharField(
        max_length=80,
        required=False,
        label="Wood quality",
        help_text="Optional value from 1 to 10.",
    )

    def has_changed(self) -> bool:
        """Treat untouched browser rows as empty despite their selected defaults."""

        if not self.is_bound:
            return super().has_changed()
        for field_name in self.fields:
            value = self.data.get(self.add_prefix(field_name))
            normalized = "" if value is None else str(value).strip()
            if not normalized:
                continue
            if normalized != self._BROWSER_DEFAULTS.get(field_name):
                return True
        return False


class RequiredRowFormSet(BaseFormSet):
    def clean(self) -> None:
        super().clean()
        if any(self.errors):
            return
        if not any(form.cleaned_data for form in self.forms):
            raise forms.ValidationError("Enter at least one result row.")


ManualResultFormSet = formset_factory(
    ManualResultRowForm,
    formset=RequiredRowFormSet,
    extra=3,
    max_num=25,
    validate_max=True,
)
