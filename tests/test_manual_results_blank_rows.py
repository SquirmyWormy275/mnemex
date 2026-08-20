from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse

from mnemex.accounts.models import Account, PrivilegedRoleAssignment
from mnemex.partners.models import PartnerOrganization
from mnemex.results.models import IngestionRun
from tests.mfa_helpers import enroll_account_mfa, force_login_with_fresh_mfa

pytestmark = pytest.mark.django_db


def _authorized_results_manager() -> Account:
    account = Account.objects.create_user(
        email="blank-row-regression@mnemex.example.invalid",
        password=None,
    )
    enroll_account_mfa(account)
    PrivilegedRoleAssignment.objects.create(
        account=account,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        assigned_by=account,
    )
    return account


def _complete_row(index: int) -> dict[str, str]:
    prefix = f"rows-{index}"
    return {
        f"{prefix}-source_result_id": "manual-complete",
        f"{prefix}-source_revision": "1",
        f"{prefix}-source_event_id": "synthetic-show-2026",
        f"{prefix}-event_name": "Synthetic Summer Show",
        f"{prefix}-result_date": "2026-07-18",
        f"{prefix}-competitor_name": "Synthetic Competitor",
        f"{prefix}-discipline": "UNDERHAND",
        f"{prefix}-score_type": "time",
        f"{prefix}-score": "12.34",
        f"{prefix}-heat_id": "",
        f"{prefix}-wood_species": "",
        f"{prefix}-wood_diameter_mm": "",
        f"{prefix}-wood_quality": "",
    }


def _browser_blank_row(index: int) -> dict[str, str]:
    prefix = f"rows-{index}"
    return {
        f"{prefix}-source_result_id": "",
        f"{prefix}-source_revision": "",
        f"{prefix}-source_event_id": "",
        f"{prefix}-event_name": "",
        f"{prefix}-result_date": "",
        f"{prefix}-competitor_name": "",
        f"{prefix}-discipline": "UNDERHAND",
        f"{prefix}-score_type": "time",
        f"{prefix}-score": "",
        f"{prefix}-heat_id": "",
        f"{prefix}-wood_species": "",
        f"{prefix}-wood_diameter_mm": "",
        f"{prefix}-wood_quality": "",
    }


def _post_data(organization: PartnerOrganization) -> dict[str, str]:
    data = {
        "organization": str(organization.pk),
        "operator_key": "blank-row-regression",
        "rows-TOTAL_FORMS": "3",
        "rows-INITIAL_FORMS": "0",
        "rows-MIN_NUM_FORMS": "0",
        "rows-MAX_NUM_FORMS": "25",
    }
    data.update(_complete_row(0))
    data.update(_browser_blank_row(1))
    data.update(_browser_blank_row(2))
    return data


def test_manual_entry_ignores_browser_blank_extra_rows() -> None:
    actor = _authorized_results_manager()
    organization = PartnerOrganization.objects.create(name="Synthetic Blank Row Show")
    client = Client()
    force_login_with_fresh_mfa(client, actor)

    response = client.post(reverse("results:manual"), _post_data(organization))

    assert response.status_code == 302
    run = IngestionRun.objects.get()
    assert (run.total_rows, run.published_rows, run.quarantined_rows) == (1, 1, 0)


def test_manual_entry_still_rejects_partially_filled_extra_row() -> None:
    actor = _authorized_results_manager()
    organization = PartnerOrganization.objects.create(name="Synthetic Partial Row Show")
    client = Client()
    force_login_with_fresh_mfa(client, actor)
    data = _post_data(organization)
    data["rows-1-source_result_id"] = "partial-row"

    response = client.post(reverse("results:manual"), data)

    assert response.status_code == 200
    body = response.content.decode()
    assert "This field is required" in body
    assert IngestionRun.objects.count() == 0
