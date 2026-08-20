from __future__ import annotations

from typing import Any, cast

from django import forms
from django.db.models import Prefetch

from mnemex.career.models import CareerAssertionRevision
from mnemex.people.models import Alias, Person


class PersonChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, person: Person) -> str:
        public_aliases = getattr(person, "public_identity_aliases", None)
        approved_alias = next(
            (
                alias.value
                for alias in (
                    public_aliases
                    if public_aliases is not None
                    else person.aliases.filter(
                        review_state=Alias.ReviewState.APPROVED,
                        is_public=True,
                    )
                )
                if alias.review_state == Alias.ReviewState.APPROVED and alias.is_public
            ),
            None,
        )
        return approved_alias or f"MNEMEX person {person.pk}"


class IdentityResolutionForm(forms.Form):
    person = PersonChoiceField(queryset=Person.objects.none())
    authorization_basis_type = forms.ChoiceField(
        choices=CareerAssertionRevision.AuthorizationBasis.choices
    )
    consent_grant_id = forms.UUIDField(
        required=False,
        label="Consent grant ID",
        help_text=(
            "Required for competitor or guardian consent. Enter the opaque MNEMEX grant UUID."
        ),
    )
    authorization_basis_reference = forms.CharField(
        max_length=240,
        required=False,
        help_text=("Required only for source-data-rights or show-finalization-policy evidence."),
    )
    authorization_captured_at = forms.DateTimeField(
        help_text="The timezone-aware date and time when this authority was captured.",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    operator_key = forms.CharField(
        max_length=200,
        help_text="A unique key makes an exact retry safe.",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        person_field = cast(forms.ModelChoiceField, self.fields["person"])
        person_field.queryset = Person.objects.filter(status=Person.Status.ACTIVE).prefetch_related(
            Prefetch(
                "aliases",
                queryset=Alias.objects.filter(
                    review_state=Alias.ReviewState.APPROVED,
                    is_public=True,
                ).order_by("created_at"),
                to_attr="public_identity_aliases",
            )
        )

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean() or {}
        basis = cleaned.get("authorization_basis_type")
        grant_id = cleaned.get("consent_grant_id")
        reference = str(cleaned.get("authorization_basis_reference") or "").strip()
        consent_bases = {
            CareerAssertionRevision.AuthorizationBasis.COMPETITOR_CONSENT,
            CareerAssertionRevision.AuthorizationBasis.GUARDIAN_CONSENT,
        }
        if basis in consent_bases:
            if grant_id is None:
                self.add_error("consent_grant_id", "A consent grant ID is required for this basis.")
            cleaned["authorization_basis_reference"] = ""
        else:
            if not reference:
                self.add_error(
                    "authorization_basis_reference",
                    "An evidence reference is required for this basis.",
                )
            if grant_id is not None:
                self.add_error(
                    "consent_grant_id",
                    "Consent grant evidence is only valid for a consent basis.",
                )
            cleaned["authorization_basis_reference"] = reference
        return cleaned
