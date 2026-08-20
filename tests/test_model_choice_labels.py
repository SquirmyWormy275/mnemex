from __future__ import annotations

import pytest

from mnemex.accounts.models import Account, PrivilegedRoleAssignment
from mnemex.partners.models import PartnerOrganization
from mnemex.results.forms import SpreadsheetUploadForm
from mnemex.results.models import MappingTemplate
from tests.mfa_helpers import enroll_account_mfa

pytestmark = pytest.mark.django_db


def test_results_desk_choice_labels_are_human_readable_and_hide_internal_ids() -> None:
    actor = Account.objects.create(email="choice-labels@mnemex.example.invalid")
    enroll_account_mfa(actor)
    PrivilegedRoleAssignment.objects.create(
        account=actor,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        assigned_by=actor,
    )
    organization = PartnerOrganization.objects.create(name="Synthetic Label Show")
    mapping = MappingTemplate.objects.create(
        organization=organization,
        name="Standard results",
        version=3,
        field_map={},
        created_by=actor,
    )

    form = SpreadsheetUploadForm(actor=actor)
    organization_choices = dict(form.fields["organization"].choices)
    mapping_choices = dict(form.fields["mapping_template"].choices)

    assert organization_choices[organization.pk] == "Synthetic Label Show"
    assert mapping_choices[mapping.pk] == "Standard results (v3)"
    assert str(organization.pk) not in organization_choices[organization.pk]
    assert str(mapping.pk) not in mapping_choices[mapping.pk]
