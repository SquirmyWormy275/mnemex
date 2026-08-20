from __future__ import annotations

import hashlib
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from mnemex.accounts.models import Account, PrivilegedRoleAssignment
from mnemex.legacy_migration.models import LegacySourceInventory
from mnemex.partners.models import PartnerOrganization
from mnemex.results.artifact_lifecycle import reconcile_artifact_objects
from mnemex.results.artifacts import LocalPrivateArtifactStore
from mnemex.results.models import ArtifactObjectWrite, MappingTemplate, SourceArtifact
from tests.mfa_helpers import enroll_account_mfa, force_login_with_fresh_mfa

pytestmark = pytest.mark.django_db


def test_private_artifact_store_reads_only_contained_references(tmp_path: Path) -> None:
    store = LocalPrivateArtifactStore(tmp_path)
    content = b"synthetic private artifact"
    reference = store.put(content=content, filename="synthetic.xlsx")

    assert store.read(reference=reference) == content
    with pytest.raises(ValueError, match="below the private artifact root"):
        store.read(reference="../outside.xlsx")


def _actor() -> Account:
    actor = Account.objects.create_user(
        email="synthetic-artifact-lifecycle@mnemex.example.invalid",
        password="synthetic-password-123",
    )
    enroll_account_mfa(actor)
    PrivilegedRoleAssignment.objects.create(
        account=actor,
        role=PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
        assigned_by=actor,
    )
    return actor


def _mapping(
    organization: PartnerOrganization, actor: Account, *, valid: bool = True
) -> MappingTemplate:
    field_map = {
        "source_result_id": "result_id",
        "source_revision": "revision",
        "source_event_id": "event_id",
        "event_name": "event_name",
        "result_date": "result_date",
        "competitor_name": "competitor",
        "discipline": "event",
        "score_type": "score_kind",
        "score": "result",
    }
    if not valid:
        field_map.pop("source_result_id")
    return MappingTemplate.objects.create(
        organization=organization,
        name="Valid" if valid else "Invalid",
        version=1,
        field_map=field_map,
        created_by=actor,
    )


def _post(
    client: Client,
    organization: PartnerOrganization,
    mapping: MappingTemplate,
    *,
    operator_key: str,
    content: bytes,
) -> Any:
    return client.post(
        reverse("results:upload"),
        {
            "organization": str(organization.pk),
            "mapping_template": str(mapping.pk),
            "operator_key": operator_key,
            "spreadsheet": SimpleUploadedFile("results.csv", content, content_type="text/csv"),
        },
    )


def _valid_csv(result_id: str) -> bytes:
    return (
        "result_id,revision,event_id,event_name,result_date,competitor,event,score_kind,result\n"
        f"{result_id},1,show-2026,Synthetic Show,2026-07-18,Synthetic,UNDERHAND,time,10.2\n"
    ).encode()


def _reconcile(artifact_root: Path) -> None:
    reconcile_artifact_objects(
        store=LocalPrivateArtifactStore(artifact_root),
        now=timezone.now() + timedelta(hours=1),
        limit=100,
    )


def _legacy_xlsx() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Synthetic Results"
    sheet.append(["Result ID", "Competitor", "Score"])
    sheet.append(["synthetic-1", "Synthetic Competitor", "10.2"])
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


def test_parse_failure_records_then_reconciles_an_unreferenced_private_object(
    tmp_path: Path,
) -> None:
    actor = _actor()
    organization = PartnerOrganization.objects.create(name="Synthetic Parse Failure Show")
    mapping = _mapping(organization, actor)
    client = Client()
    force_login_with_fresh_mfa(client, actor)

    with override_settings(MNEMEX_PRIVATE_ARTIFACT_ROOT=tmp_path):
        response = _post(
            client,
            organization,
            mapping,
            operator_key="parse-failure",
            content=b"\xff\xfeinvalid utf-8",
        )

    assert response.status_code == 200
    assert "CSV files must use UTF-8 encoding" in response.content.decode()
    assert SourceArtifact.objects.count() == 0
    write = ArtifactObjectWrite.objects.get()
    assert write.status == ArtifactObjectWrite.Status.ABANDONED
    assert (tmp_path / write.artifact_object.object_reference).is_file()

    _reconcile(tmp_path)

    write.refresh_from_db()
    assert write.status == ArtifactObjectWrite.Status.CLEANED
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_mapping_failure_keeps_a_referenced_preexisting_deduplicated_object(
    tmp_path: Path,
) -> None:
    actor = _actor()
    organization = PartnerOrganization.objects.create(name="Synthetic Dedup Show")
    good_mapping = _mapping(organization, actor)
    bad_mapping = _mapping(organization, actor, valid=False)
    client = Client()
    force_login_with_fresh_mfa(client, actor)
    content = _valid_csv("dedup-1")

    with override_settings(MNEMEX_PRIVATE_ARTIFACT_ROOT=tmp_path):
        first = _post(
            client,
            organization,
            good_mapping,
            operator_key="dedup-good",
            content=content,
        )
        artifact = SourceArtifact.objects.get()
        target = tmp_path / artifact.object_reference
        second = _post(
            client,
            organization,
            bad_mapping,
            operator_key="dedup-bad-mapping",
            content=content,
        )

    assert first.status_code == 302
    assert second.status_code == 200
    assert "mapping template is missing canonical fields" in second.content.decode()
    assert SourceArtifact.objects.count() == 1
    assert target.read_bytes() == content
    assert (
        ArtifactObjectWrite.objects.filter(status=ArtifactObjectWrite.Status.ABANDONED).count() == 1
    )

    _reconcile(tmp_path)

    assert not ArtifactObjectWrite.objects.filter(
        status=ArtifactObjectWrite.Status.ABANDONED
    ).exists()
    assert target.read_bytes() == content


def test_idempotency_conflict_removes_only_the_new_unreferenced_object(tmp_path: Path) -> None:
    actor = _actor()
    organization = PartnerOrganization.objects.create(name="Synthetic Conflict Show")
    mapping = _mapping(organization, actor)
    client = Client()
    force_login_with_fresh_mfa(client, actor)
    first_content = _valid_csv("conflict-1")
    conflicting_content = _valid_csv("conflict-2")

    with override_settings(MNEMEX_PRIVATE_ARTIFACT_ROOT=tmp_path):
        first = _post(
            client,
            organization,
            mapping,
            operator_key="same-key",
            content=first_content,
        )
        artifact = SourceArtifact.objects.get()
        original_target = tmp_path / artifact.object_reference
        conflict = _post(
            client,
            organization,
            mapping,
            operator_key="same-key",
            content=conflicting_content,
        )

    conflicting_digest = hashlib.sha256(conflicting_content).hexdigest()
    assert first.status_code == 302
    assert conflict.status_code == 200
    assert "different payload" in conflict.content.decode()
    assert original_target.read_bytes() == first_content
    conflicting_write = ArtifactObjectWrite.objects.exclude(
        artifact_object__digest=artifact.digest
    ).get()
    assert conflicting_write.status == ArtifactObjectWrite.Status.ABANDONED

    _reconcile(tmp_path)

    conflicting_write.refresh_from_db()
    assert conflicting_write.status == ArtifactObjectWrite.Status.CLEANED
    assert not list(tmp_path.rglob(f"{conflicting_digest}.*"))


def test_legacy_database_rollback_is_durably_tracked_before_orphan_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _actor()
    organization = PartnerOrganization.objects.create(name="Synthetic Legacy Rollback Show")
    client = Client()
    force_login_with_fresh_mfa(client, actor)

    def fail_inventory_create(**_kwargs: object) -> None:
        raise IntegrityError("synthetic post-write database failure")

    monkeypatch.setattr(LegacySourceInventory.objects, "create", fail_inventory_create)
    with override_settings(MNEMEX_PRIVATE_ARTIFACT_ROOT=tmp_path):
        response = client.post(
            reverse("legacy_migration:upload"),
            {
                "organization": str(organization.pk),
                "source_key": "synthetic-rollback-source",
                "data_rights_reference": "synthetic-test-authorization",
                "spreadsheet": SimpleUploadedFile(
                    "synthetic-rollback.xlsx",
                    _legacy_xlsx(),
                    content_type=(
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    ),
                ),
            },
        )

    assert response.status_code == 200
    assert SourceArtifact.objects.count() == 0
    write = ArtifactObjectWrite.objects.get()
    assert write.status == ArtifactObjectWrite.Status.ABANDONED
    assert (tmp_path / write.artifact_object.object_reference).is_file()

    _reconcile(tmp_path)

    write.refresh_from_db()
    assert write.status == ArtifactObjectWrite.Status.CLEANED
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
