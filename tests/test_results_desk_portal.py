from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from mnemex.accounts.models import Account, PrivilegedRoleAssignment
from mnemex.partners.models import PartnerOrganization
from mnemex.results.models import IngestionRun, MappingTemplate, SourceArtifact
from tests.mfa_helpers import enroll_account_mfa, force_login_with_fresh_mfa

pytestmark = pytest.mark.django_db

STANDARD_HEADERS = [
    "source_result_id",
    "source_revision",
    "source_event_id",
    "event_name",
    "result_date",
    "competitor_name",
    "discipline",
    "score_type",
    "score",
    "heat_id",
    "wood_species",
    "wood_diameter_mm",
    "wood_quality",
]


def _account(email: str, *, authorized: bool = True) -> Account:
    account = Account.objects.create_user(email=email, password="synthetic-password-123")
    if authorized:
        enroll_account_mfa(account)
        PrivilegedRoleAssignment.objects.create(
            account=account,
            role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
            assigned_by=account,
        )
    return account


def _mapping(organization: PartnerOrganization, actor: Account) -> MappingTemplate:
    return MappingTemplate.objects.create(
        organization=organization,
        name="Standard",
        version=1,
        field_map={
            "source_result_id": "result_id",
            "source_revision": "revision",
            "source_event_id": "event_id",
            "event_name": "event_name",
            "result_date": "result_date",
            "competitor_name": "competitor",
            "discipline": "event",
            "score_type": "score_kind",
            "score": "result",
            "heat_id": "heat_id",
            "wood_species": "wood_species",
            "wood_diameter_mm": "wood_diameter_mm",
            "wood_quality": "wood_quality",
        },
        created_by=actor,
    )


def _manual_post(organization: PartnerOrganization, operator_key: str) -> dict[str, object]:
    return {
        "organization": str(organization.pk),
        "operator_key": operator_key,
        "rows-TOTAL_FORMS": "2",
        "rows-INITIAL_FORMS": "0",
        "rows-MIN_NUM_FORMS": "0",
        "rows-MAX_NUM_FORMS": "25",
        "rows-0-source_result_id": "manual-valid",
        "rows-0-source_revision": "1",
        "rows-0-source_event_id": "synthetic-show-2026",
        "rows-0-event_name": "Synthetic Summer Show",
        "rows-0-result_date": "2026-07-18",
        "rows-0-competitor_name": "Synthetic Competitor",
        "rows-0-discipline": "UNDERHAND",
        "rows-0-score_type": "time",
        "rows-0-score": "12.34",
        "rows-0-heat_id": "heat-1",
        "rows-0-wood_species": "white pine",
        "rows-0-wood_diameter_mm": "325",
        "rows-0-wood_quality": "8",
        "rows-1-source_result_id": "manual-invalid",
        "rows-1-source_revision": "1",
        "rows-1-source_event_id": "synthetic-show-2026",
        "rows-1-event_name": "Synthetic Summer Show",
        "rows-1-result_date": "2026-07-18",
        "rows-1-competitor_name": "Synthetic Competitor Two",
        "rows-1-discipline": "UNDERHAND",
        "rows-1-score_type": "time",
        "rows-1-score": "not-a-number",
    }


def test_dashboard_requires_login_and_mfa_bound_results_manager() -> None:
    anonymous = Client()
    response = anonymous.get(reverse("results:dashboard"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))

    unauthorized = Client()
    unauthorized.force_login(_account("ordinary@mnemex.example.invalid", authorized=False))
    assert unauthorized.get(reverse("results:dashboard")).status_code == 403

    authorized = Client()
    force_login_with_fresh_mfa(authorized, _account("gillian@mnemex.example.invalid"))
    response = authorized.get(reverse("results:dashboard"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Results Desk" in body
    assert "Spreadsheet upload" in body
    assert "Recommended" in body
    assert "Manual entry" in body
    assert "does not write to STRATHMARK" in body


def test_starter_csv_requires_results_access_and_contains_only_synthetic_standard_data() -> None:
    anonymous = Client()
    response = anonymous.get(reverse("results:starter-csv"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))

    unauthorized = Client()
    unauthorized.force_login(_account("starter-denied@mnemex.example.invalid", authorized=False))
    assert unauthorized.get(reverse("results:starter-csv")).status_code == 403

    authorized = Client()
    force_login_with_fresh_mfa(authorized, _account("starter-allowed@mnemex.example.invalid"))
    response = authorized.get(reverse("results:starter-csv"))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert response["Content-Disposition"] == 'attachment; filename="mnemex-results-starter.csv"'
    assert response["X-Content-Type-Options"] == "nosniff"
    rows = list(csv.DictReader(StringIO(response.content.decode("utf-8"))))
    assert rows
    assert list(rows[0]) == STANDARD_HEADERS
    assert "synthetic" in rows[0]["competitor_name"].lower()
    assert rows[0]["wood_species"] == "Pine"
    assert "@" not in response.content.decode("utf-8")


def test_upload_defaults_to_standard_columns_without_a_preexisting_mapping(tmp_path: Path) -> None:
    actor = _account("standard-upload@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Standard Upload Show")
    client = Client()
    force_login_with_fresh_mfa(client, actor)
    content = (
        ",".join(STANDARD_HEADERS)
        + "\nstandard-1,1,show-2026,Synthetic Show,2026-07-18,Synthetic Competitor,UNDERHAND,time,10.2,heat-1,white pine,325,8\n"
    ).encode()

    upload_page = client.get(reverse("results:upload"))
    assert upload_page.status_code == 200
    mapping_field = upload_page.context["form"].fields["mapping_template"]
    assert mapping_field.required is False
    assert "recommended" in str(mapping_field.empty_label).lower()

    with override_settings(MNEMEX_PRIVATE_ARTIFACT_ROOT=tmp_path):
        response = client.post(
            reverse("results:upload"),
            {
                "organization": str(organization.pk),
                "operator_key": "standard-no-mapping",
                "spreadsheet": SimpleUploadedFile("results.csv", content, content_type="text/csv"),
            },
        )

    assert response.status_code == 302
    run = IngestionRun.objects.get()
    assert run.published_rows == 1
    assert run.mapping_template.name == "MNEMEX standard columns"
    assert run.mapping_template.version == 1
    assert run.mapping_template.field_map == {header: header for header in STANDARD_HEADERS}


def test_standard_mapping_is_reused_across_uploads(tmp_path: Path) -> None:
    actor = _account("standard-reuse@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Standard Reuse Show")
    client = Client()
    force_login_with_fresh_mfa(client, actor)

    with override_settings(MNEMEX_PRIVATE_ARTIFACT_ROOT=tmp_path):
        for index in (1, 2):
            content = (
                ",".join(STANDARD_HEADERS)
                + f"\nstandard-{index},1,show-2026,Synthetic Show,2026-07-18,Synthetic {index},UNDERHAND,time,10.{index},,,,\n"
            ).encode()
            response = client.post(
                reverse("results:upload"),
                {
                    "organization": str(organization.pk),
                    "operator_key": f"standard-reuse-{index}",
                    "spreadsheet": SimpleUploadedFile(
                        f"results-{index}.csv", content, content_type="text/csv"
                    ),
                },
            )
            assert response.status_code == 302

    assert IngestionRun.objects.count() == 2
    mappings = MappingTemplate.objects.filter(
        organization=organization, name="MNEMEX standard columns"
    )
    assert mappings.count() == 1
    assert set(IngestionRun.objects.values_list("mapping_template_id", flat=True)) == {
        mappings.get().pk
    }


def test_results_portal_lists_only_accessible_organizations_and_denies_cross_tenant_post() -> None:
    actor = _account("scoped-portal@mnemex.example.invalid", authorized=False)
    actor.mfa_enrolled_at = timezone.now()
    actor.save(update_fields=["mfa_enrolled_at"])
    organization_a = PartnerOrganization.objects.create(name="Visible Scoped Portal Show")
    organization_b = PartnerOrganization.objects.create(name="Hidden Scoped Portal Show")
    PrivilegedRoleAssignment.objects.create(
        account=actor,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        assigned_by=actor,
        scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
        organization=organization_a,
    )
    _mapping(organization_a, actor)
    _mapping(organization_b, actor)
    client = Client()
    force_login_with_fresh_mfa(client, actor)

    upload = client.get(reverse("results:upload"))
    assert upload.status_code == 200
    organization_ids = set(
        upload.context["form"]
        .fields["organization"]
        .queryset.values_list("organization_id", flat=True)
    )
    mapping_organization_ids = set(
        upload.context["form"]
        .fields["mapping_template"]
        .queryset.values_list("organization_id", flat=True)
    )
    assert organization_ids == {organization_a.pk}
    assert mapping_organization_ids == {organization_a.pk}

    response = client.post(
        reverse("results:manual"), _manual_post(organization_b, "cross-tenant-denied")
    )
    assert response.status_code == 403
    assert IngestionRun.objects.count() == 0

    upload = client.post(
        reverse("results:upload"),
        {
            "organization": str(organization_b.pk),
            "operator_key": "cross-tenant-standard-denied",
            "spreadsheet": SimpleUploadedFile(
                "results.csv", b"header\nvalue\n", content_type="text/csv"
            ),
        },
    )
    assert upload.status_code == 403
    assert not MappingTemplate.objects.filter(
        organization=organization_b, name="MNEMEX standard columns"
    ).exists()
    assert SourceArtifact.objects.count() == 0

    cross_tenant_mapping = MappingTemplate.objects.get(organization=organization_b)
    upload = client.post(
        reverse("results:upload"),
        {
            "organization": str(organization_a.pk),
            "mapping_template": str(cross_tenant_mapping.pk),
            "operator_key": "cross-tenant-mapping-denied",
            "spreadsheet": SimpleUploadedFile(
                "results.csv", b"header\nvalue\n", content_type="text/csv"
            ),
        },
    )
    assert upload.status_code == 403
    assert SourceArtifact.objects.count() == 0


def test_results_manager_can_create_a_mapping_template() -> None:
    actor = _account("mapping@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Mapping Show")
    client = Client()
    force_login_with_fresh_mfa(client, actor)

    response = client.post(
        reverse("results:mapping-create"),
        {
            "organization": str(organization.pk),
            "name": "Show export",
            "source_result_id": "Result ID",
            "source_revision": "Revision",
            "source_event_id": "Event ID",
            "event_name": "Show Name",
            "result_date": "Result Date",
            "competitor_name": "Competitor",
            "discipline": "Event",
            "score_type": "Score Type",
            "score": "Score",
            "heat_id": "Heat",
            "wood_species": "Wood Species",
            "wood_diameter_mm": "Wood Diameter",
            "wood_quality": "Wood Quality",
        },
    )

    assert response.status_code == 302
    mapping = MappingTemplate.objects.get(organization=organization, name="Show export")
    assert mapping.version == 1
    assert mapping.field_map["competitor_name"] == "Competitor"
    assert mapping.field_map["source_event_id"] == "Event ID"
    assert mapping.field_map["wood_quality"] == "Wood Quality"
    assert mapping.created_by == actor


def test_manual_entry_uses_canonical_mapping_and_shows_mixed_batch() -> None:
    actor = _account("manual-portal@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Manual Portal Show")
    client = Client()
    force_login_with_fresh_mfa(client, actor)

    response = client.post(reverse("results:manual"), _manual_post(organization, "manual-ui-1"))

    assert response.status_code == 302
    run = IngestionRun.objects.get()
    assert response.url == reverse("results:run-detail", kwargs={"run_id": run.pk})
    assert (run.total_rows, run.published_rows, run.quarantined_rows) == (2, 1, 1)
    assert run.mapping_template.field_map == {
        "source_result_id": "source_result_id",
        "source_revision": "source_revision",
        "source_event_id": "source_event_id",
        "event_name": "event_name",
        "result_date": "result_date",
        "competitor_name": "competitor_name",
        "discipline": "discipline",
        "score_type": "score_type",
        "score": "score",
        "heat_id": "heat_id",
        "wood_species": "wood_species",
        "wood_diameter_mm": "wood_diameter_mm",
        "wood_quality": "wood_quality",
    }

    detail = client.get(response.url)
    assert detail.status_code == 200
    body = detail.content.decode()
    assert "manual-invalid" in body
    assert "Synthetic Summer Show" in body
    assert "2026-07-18" in body
    assert "UNDERHAND" in body
    assert "12.34" in body
    assert "Enter a numeric score." in body
    assert "Quarantined" in body


@override_settings(MNEMEX_PRIVATE_ARTIFACT_ROOT=None)
def test_upload_requires_an_explicit_private_artifact_root() -> None:
    actor = _account("no-store@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic No Store Show")
    mapping = _mapping(organization, actor)
    client = Client()
    force_login_with_fresh_mfa(client, actor)

    response = client.post(
        reverse("results:upload"),
        {
            "organization": str(organization.pk),
            "mapping_template": str(mapping.pk),
            "operator_key": "missing-store",
            "spreadsheet": SimpleUploadedFile(
                "results.csv",
                b"result_id,revision,event_id,event_name,result_date,competitor,event,score_kind,result,heat_id,wood_species,wood_diameter_mm,wood_quality\n1,1,show-2026,Synthetic Show,2026-07-18,A,UNDERHAND,time,10,,,,\n",
                content_type="text/csv",
            ),
        },
    )

    assert response.status_code == 200
    assert "Private artifact storage is not configured" in response.content.decode()
    assert SourceArtifact.objects.count() == 0


def test_csv_upload_uses_private_digest_reference_and_replays(tmp_path: Path) -> None:
    actor = _account("upload-portal@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Upload Portal Show")
    mapping = _mapping(organization, actor)
    client = Client()
    force_login_with_fresh_mfa(client, actor)
    content = b"result_id,revision,event_id,event_name,result_date,competitor,event,score_kind,result,heat_id,wood_species,wood_diameter_mm,wood_quality\ncsv-1,1,show-2026,Synthetic Show,2026-07-18,Synthetic,UNDERHAND,time,10.2,,,,\n"
    post = {
        "organization": str(organization.pk),
        "mapping_template": str(mapping.pk),
        "operator_key": "upload-ui-1",
    }

    with override_settings(MNEMEX_PRIVATE_ARTIFACT_ROOT=tmp_path):
        first = client.post(
            reverse("results:upload"),
            {
                **post,
                "spreadsheet": SimpleUploadedFile("results.csv", content, content_type="text/csv"),
            },
        )
        second = client.post(
            reverse("results:upload"),
            {
                **post,
                "spreadsheet": SimpleUploadedFile("results.csv", content, content_type="text/csv"),
            },
        )

    assert first.status_code == second.status_code == 302
    artifact = SourceArtifact.objects.get()
    reference = Path(artifact.object_reference)
    assert not reference.is_absolute()
    assert artifact.digest in reference.name
    assert (tmp_path / reference).read_bytes() == content
    assert IngestionRun.objects.count() == 1
    assert IngestionRun.objects.get().mapping_template == mapping
    assert "replayed=1" in second.url

    replay_detail = client.get(second.url)
    assert "This submission was an exact replay" in replay_detail.content.decode()


def test_invalid_upload_and_manual_form_render_actionable_errors(tmp_path: Path) -> None:
    actor = _account("invalid-portal@mnemex.example.invalid")
    organization = PartnerOrganization.objects.create(name="Synthetic Invalid Portal Show")
    mapping = _mapping(organization, actor)
    client = Client()
    force_login_with_fresh_mfa(client, actor)

    with override_settings(MNEMEX_PRIVATE_ARTIFACT_ROOT=tmp_path):
        upload = client.post(
            reverse("results:upload"),
            {
                "organization": str(organization.pk),
                "mapping_template": str(mapping.pk),
                "operator_key": "bad-upload",
                "spreadsheet": SimpleUploadedFile(
                    "results.txt", b"not a spreadsheet", content_type="text/plain"
                ),
            },
        )
    assert upload.status_code == 200
    assert "Upload a CSV or XLSX file" in upload.content.decode()

    with override_settings(MNEMEX_PRIVATE_ARTIFACT_ROOT=tmp_path):
        oversized = client.post(
            reverse("results:upload"),
            {
                "organization": str(organization.pk),
                "mapping_template": str(mapping.pk),
                "operator_key": "oversized-upload",
                "spreadsheet": SimpleUploadedFile(
                    "results.csv",
                    b"x" * (5 * 1024 * 1024 + 1),
                    content_type="text/csv",
                ),
            },
        )
    assert oversized.status_code == 200
    assert "Spreadsheet must contain 1 byte to 5 MiB" in oversized.content.decode()

    manual = client.post(
        reverse("results:manual"),
        {
            "organization": str(organization.pk),
            "operator_key": "empty-manual",
            "rows-TOTAL_FORMS": "1",
            "rows-INITIAL_FORMS": "0",
            "rows-MIN_NUM_FORMS": "0",
            "rows-MAX_NUM_FORMS": "25",
        },
    )
    assert manual.status_code == 200
    assert "Enter at least one result row" in manual.content.decode()
    assert IngestionRun.objects.count() == 0
