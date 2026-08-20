from __future__ import annotations

import hashlib
import json
import uuid
from csv import DictReader
from datetime import datetime
from datetime import timezone as dt_timezone
from io import StringIO

import pytest
from django.urls import reverse
from django.utils import timezone

from mnemex.accounts.models import Account, PrivilegedRoleAssignment
from mnemex.career.models import CareerAssertionRevision
from mnemex.career.services import reconcile_identity
from mnemex.export.models import EvidenceSnapshotManifest, ExportEligibilityRevision
from mnemex.export.services import review_export_eligibility
from mnemex.partners.models import PartnerOrganization
from mnemex.people.models import Alias, Person
from mnemex.results.models import (
    IngestionRun,
    MappingTemplate,
    PublishedSourceResult,
    ReconciliationCase,
    SourceArtifact,
    StagedResult,
)
from tests.mfa_helpers import (
    enroll_account_mfa,
    force_login_with_fresh_mfa,
    verify_account_email,
)

pytestmark = pytest.mark.django_db
UTC = dt_timezone.utc


def _actor(
    label: str,
    organization: PartnerOrganization,
    *roles: PrivilegedRoleAssignment.Role,
    mfa: bool = True,
) -> Account:
    actor = Account.objects.create_user(
        email=f"{label}-{uuid.uuid4()}@mnemex.example.invalid",
        password=None,
    )
    verify_account_email(actor)
    if mfa:
        enroll_account_mfa(actor)
    for role in roles:
        PrivilegedRoleAssignment.objects.create(
            account=actor,
            role=role,
            scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
            organization=organization,
            assigned_by=actor,
        )
    return actor


def _case(
    organization: PartnerOrganization,
    actor: Account,
    label: str,
    *,
    wood_species: str = "Pine",
) -> ReconciliationCase:
    digest = hashlib.sha256(label.encode()).hexdigest()
    artifact = SourceArtifact.objects.create(
        organization=organization,
        kind=SourceArtifact.Kind.MANUAL_MANIFEST,
        digest=digest,
        original_name="synthetic-manual-entry.json",
        content_type="application/vnd.mnemex.manual+json",
        byte_size=128,
        uploaded_by=actor,
    )
    mapping = MappingTemplate.objects.create(
        organization=organization,
        name=f"synthetic-{label}",
        version=1,
        field_map={"synthetic": "synthetic"},
        created_by=actor,
    )
    run = IngestionRun.objects.create(
        organization=organization,
        artifact=artifact,
        mapping_template=mapping,
        operator_key=f"synthetic-{label}",
        request_digest=digest,
        created_by=actor,
    )
    payload = {
        "source_result_id": f"result-{label}",
        "source_revision": 1,
        "source_event_id": f"event-{label}",
        "event_name": f"Synthetic Event {label}",
        "result_date": "2026-07-18",
        "competitor_name": f"Synthetic Competitor {label}",
        "discipline": "UNDERHAND",
        "score_type": "time",
        "score": "12.34",
        "heat_id": "heat-1",
        "wood_species": wood_species,
        "wood_diameter_mm": 325,
        "wood_quality": 8,
    }
    staged = StagedResult.objects.create(
        run=run,
        row_number=1,
        source_result_id=payload["source_result_id"],
        source_revision=1,
        normalized_payload=payload,
        payload_digest=digest,
        validation_errors=[],
        outcome=StagedResult.Outcome.PUBLISHED,
        proposed_person_ids=[],
    )
    published = PublishedSourceResult.objects.create(
        organization=organization,
        source_result_id=payload["source_result_id"],
        source_revision=1,
        discipline="UNDERHAND",
        score_type="time",
        normalized_payload=payload,
        payload_digest=digest,
        artifact=artifact,
        staged_result=staged,
    )
    run.status = IngestionRun.Status.COMPLETED
    run.total_rows = 1
    run.published_rows = 1
    run.completed_at = timezone.now()
    run.save()
    return ReconciliationCase.objects.create(
        case_type=ReconciliationCase.CaseType.IDENTITY_UNRESOLVED,
        staged_result=staged,
        existing_published_result=published,
        details={"reason": "synthetic explicit review"},
    )


def _assertion(
    organization: PartnerOrganization,
    actor: Account,
    label: str,
    *,
    wood_species: str = "Pine",
) -> CareerAssertionRevision:
    case = _case(organization, actor, label, wood_species=wood_species)
    return reconcile_identity(
        actor=actor,
        organization=organization,
        reconciliation_case=case,
        person=Person.objects.create(),
        authorization_basis_type=CareerAssertionRevision.AuthorizationBasis.SOURCE_DATA_RIGHTS,
        authorization_basis_reference="synthetic-policy:results-rights:v1",
        authorization_captured_at=datetime(2026, 8, 1, 10, 0, tzinfo=UTC),
        operator_key=f"identity-{label}",
    ).assertion


def test_identity_queue_requires_login_mfa_role_and_filters_tenants(client) -> None:
    own = PartnerOrganization.objects.create(name="Synthetic Own Review Show")
    other = PartnerOrganization.objects.create(name="Synthetic Other Review Show")
    reviewer = _actor("identity", own, PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER)
    no_mfa = _actor("no-mfa", own, PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER, mfa=False)
    own_case = _case(own, reviewer, "own-visible")
    _case(other, reviewer, "other-hidden")

    response = client.get(reverse("career:identity-queue"))
    assert response.status_code == 302
    client.force_login(no_mfa)
    missing = client.get(reverse("career:identity-queue"))
    assert missing.status_code == 302
    assert missing.url.startswith(reverse("mfa_activate_totp"))
    force_login_with_fresh_mfa(client, reviewer)
    response = client.get(reverse("career:identity-queue"))
    assert response.status_code == 200
    assert "Synthetic Competitor own-visible" in response.content.decode()
    assert "Synthetic Competitor other-hidden" not in response.content.decode()
    assert client.get(reverse("career:identity-detail", args=[own_case.pk])).status_code == 200

    dashboard = client.get(reverse("results:dashboard"))
    assert dashboard.status_code == 200
    body = dashboard.content.decode()
    assert "Identity review" in body
    assert "Spreadsheet upload" not in body
    assert "Snapshot history" not in body


def test_identity_detail_uses_explicit_person_and_replays_without_auto_match(client) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Identity Approval")
    actor = _actor("approve", organization, PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER)
    case = _case(organization, actor, "approval")
    person = Person.objects.create()
    Alias.objects.create(
        person=person,
        value="Private Approved Synthetic Alias",
        normalized_value="private approved synthetic alias",
        source="synthetic-test",
        review_state=Alias.ReviewState.APPROVED,
    )
    Alias.objects.create(
        person=person,
        value="Public Approved Synthetic Alias",
        normalized_value="public approved synthetic alias",
        source="synthetic-public-test",
        review_state=Alias.ReviewState.APPROVED,
        is_public=True,
    )
    opaque_person = Person.objects.create()
    Alias.objects.create(
        person=opaque_person,
        value="Never Render This Private Alias",
        normalized_value="never render this private alias",
        source="synthetic-private-only-test",
        review_state=Alias.ReviewState.APPROVED,
    )
    force_login_with_fresh_mfa(client, actor)
    detail_url = reverse("career:identity-detail", args=[case.pk])
    initial_body = client.get(detail_url).content.decode()
    assert "Public Approved Synthetic Alias" in initial_body
    assert "Private Approved Synthetic Alias" not in initial_body
    assert "Never Render This Private Alias" not in initial_body
    assert f"MNEMEX person {opaque_person.pk}" in initial_body
    post = {
        "person": str(person.pk),
        "authorization_basis_type": CareerAssertionRevision.AuthorizationBasis.SOURCE_DATA_RIGHTS,
        "authorization_basis_reference": "synthetic-policy:results-rights:v1",
        "authorization_captured_at": "2026-08-01T10:00:00+00:00",
        "operator_key": "portal-identity-approval",
    }
    first = client.post(detail_url, post)
    replay = client.post(detail_url, post)
    assert first.status_code == 302
    assert replay.status_code == 302
    assert "replayed=1" in replay["Location"]
    assert CareerAssertionRevision.objects.get().person_id == person.pk

    queue_body = client.get(reverse("career:identity-queue")).content.decode()
    assert "Resolved identity history" in queue_body
    assert "Correct identity" in queue_body
    resolved_body = client.get(detail_url).content.decode()
    assert "Append identity correction" in resolved_body
    assert str(person.pk) in resolved_body
    correction_post = {
        **post,
        "person": str(opaque_person.pk),
        "operator_key": "portal-identity-correction",
    }
    corrected = client.post(detail_url, correction_post)
    corrected_replay = client.post(detail_url, correction_post)
    assert corrected.status_code == corrected_replay.status_code == 302
    assert "replayed=1" in corrected_replay["Location"]
    revisions = list(CareerAssertionRevision.objects.order_by("revision"))
    assert [revision.person_id for revision in revisions] == [person.pk, opaque_person.pk]
    assert revisions[1].predecessor_id == revisions[0].pk

    wrong = PartnerOrganization.objects.create(name="Synthetic Identity Wrong Tenant")
    wrong_case = _case(wrong, actor, "wrong-tenant")
    assert client.get(reverse("career:identity-detail", args=[wrong_case.pk])).status_code == 403


def test_export_workspace_requires_login_export_role_and_mfa(client) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Export Access")
    identity_only = _actor(
        "identity-only", organization, PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER
    )
    no_mfa = _actor(
        "export-no-mfa",
        organization,
        PrivilegedRoleAssignment.Role.EXPORT_REVIEWER,
        mfa=False,
    )

    response = client.get(reverse("export:review-queue"))
    assert response.status_code == 302
    force_login_with_fresh_mfa(client, identity_only)
    assert client.get(reverse("export:review-queue")).status_code == 403
    client.force_login(no_mfa)
    missing = client.get(reverse("export:review-queue"))
    assert missing.status_code == 302
    assert missing.url.startswith(reverse("mfa_activate_totp"))


def test_export_queue_is_tenant_scoped_and_review_is_validated_and_revisioned(client) -> None:
    own = PartnerOrganization.objects.create(name="Synthetic Export Own")
    other = PartnerOrganization.objects.create(name="Synthetic Export Other")
    actor = _actor(
        "export",
        own,
        PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER,
        PrivilegedRoleAssignment.Role.EXPORT_REVIEWER,
    )
    own_assertion = _assertion(own, actor, "own-export")
    invalid_assertion = _assertion(own, actor, "invalid-export", wood_species="white pine")
    other_actor = _actor(
        "other-export",
        other,
        PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER,
        PrivilegedRoleAssignment.Role.EXPORT_REVIEWER,
    )
    _assertion(other, other_actor, "other-export")
    force_login_with_fresh_mfa(client, actor)
    queue = client.get(reverse("export:review-queue"))
    body = queue.content.decode()
    assert queue.status_code == 200
    assert "Synthetic Event own-export" in body
    assert "Synthetic Event other-export" not in body

    invalid_detail_url = reverse("export:review-detail", args=[invalid_assertion.pk])
    invalid_service = client.post(
        invalid_detail_url,
        {
            "decision": "eligible",
            "reason": "Synthetic review reaches domain validation",
            "operator_key": "review-invalid-species",
        },
    )
    assert invalid_service.status_code == 200
    assert "species must be a STRATHMARK-safe code" in invalid_service.content.decode()

    detail_url = reverse("export:review-detail", args=[own_assertion.pk])
    invalid = client.post(
        detail_url,
        {"decision": "eligible", "reason": "", "operator_key": "review-one"},
    )
    assert invalid.status_code == 200
    assert "required" in invalid.content.decode().lower()
    assert ExportEligibilityRevision.objects.count() == 0
    first = client.post(
        detail_url,
        {
            "decision": "eligible",
            "reason": "Synthetic evidence is complete",
            "operator_key": "review-one",
        },
    )
    second = client.post(
        detail_url,
        {
            "decision": "rejected",
            "reason": "Synthetic correction excludes this row",
            "operator_key": "review-two",
        },
    )
    assert first.status_code == second.status_code == 302
    revisions = list(ExportEligibilityRevision.objects.order_by("revision"))
    assert [item.decision for item in revisions] == ["eligible", "rejected"]
    assert revisions[1].predecessor_id == revisions[0].pk


def test_snapshot_generation_detail_and_download_are_scoped_and_pii_free(client) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Snapshot Portal")
    actor = _actor(
        "snapshot",
        organization,
        PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER,
        PrivilegedRoleAssignment.Role.EXPORT_REVIEWER,
    )
    assertion = _assertion(organization, actor, "snapshot")
    review_export_eligibility(
        actor=actor,
        organization=organization,
        career_assertion=assertion,
        decision=ExportEligibilityRevision.Decision.ELIGIBLE,
        reason="Synthetic complete row",
        operator_key="snapshot-review",
    )
    force_login_with_fresh_mfa(client, actor)
    form_response = client.get(reverse("export:snapshot-create"))
    form = form_response.context["form"]
    capture_token = form["capture_token"].value()
    form_body = form_response.content.decode()
    assert "captured_at" not in form_body
    assert "server-captured" in form_body.lower()
    response = client.post(
        reverse("export:snapshot-create"),
        {
            "organization": str(organization.pk),
            "source_id": "mnemex:snapshot:portal-test",
            "cutoff": "2026-08-02",
            "capture_token": capture_token,
            "operator_key": "snapshot-portal-test",
        },
    )
    assert response.status_code == 302
    replay = client.post(
        reverse("export:snapshot-create"),
        {
            "organization": str(organization.pk),
            "source_id": "mnemex:snapshot:portal-test",
            "cutoff": "2026-08-02",
            "capture_token": capture_token,
            "operator_key": "snapshot-portal-test",
        },
    )
    assert replay.status_code == 302
    assert "replayed=1" in replay["Location"]
    snapshot = EvidenceSnapshotManifest.objects.get()
    detail = client.get(reverse("export:snapshot-detail", args=[snapshot.pk]))
    assert detail.status_code == 200
    assert len(snapshot.rows) == 1
    assert "included" in detail.content.decode()
    download = client.get(reverse("export:snapshot-download", args=[snapshot.pk]))
    assert download.status_code == 200
    assert "attachment" in download["Content-Disposition"]
    envelope = json.loads(download.content)
    assert envelope == snapshot.envelope
    serialized = json.dumps(envelope)
    for forbidden in (
        "Synthetic Competitor snapshot",
        "Synthetic Event snapshot",
        "competitor_name",
        "event_name",
        "normalized_payload",
        "alias",
        "contact",
        "legal",
    ):
        assert forbidden not in serialized

    other = PartnerOrganization.objects.create(name="Synthetic Snapshot Hidden")
    other_actor = _actor("other-snapshot", other, PrivilegedRoleAssignment.Role.EXPORT_REVIEWER)
    hidden = EvidenceSnapshotManifest.objects.create(
        organization=other,
        source_id="mnemex:snapshot:hidden",
        cutoff=snapshot.cutoff,
        captured_at=snapshot.captured_at,
        rows=[],
        exclusions=[],
        source_digest="0" * 64,
        request_digest="1" * 64,
        reviewed_by=other_actor,
    )
    assert client.get(reverse("export:snapshot-detail", args=[hidden.pk])).status_code == 403
    assert client.get(reverse("export:snapshot-download", args=[hidden.pk])).status_code == 403
    assert (
        client.get(reverse("export:snapshot-exclusions-download", args=[hidden.pk])).status_code
        == 403
    )


def test_snapshot_capture_token_is_actor_bound_and_cannot_be_forged(client) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Signed Capture")
    actor = _actor("signed-capture", organization, PrivilegedRoleAssignment.Role.EXPORT_REVIEWER)
    other = _actor("other-capture", organization, PrivilegedRoleAssignment.Role.EXPORT_REVIEWER)
    force_login_with_fresh_mfa(client, actor)
    token = client.get(reverse("export:snapshot-create")).context["form"]["capture_token"].value()
    payload = {
        "organization": str(organization.pk),
        "source_id": "mnemex:snapshot:signed-capture",
        "cutoff": "2026-08-02",
        "capture_token": f"{token}forged",
        "operator_key": "signed-capture",
    }
    forged = client.post(reverse("export:snapshot-create"), payload)
    assert forged.status_code == 200
    assert "capture token is invalid or expired" in forged.content.decode().lower()
    assert EvidenceSnapshotManifest.objects.count() == 0

    force_login_with_fresh_mfa(client, other)
    wrong_actor = client.post(
        reverse("export:snapshot-create"), {**payload, "capture_token": token}
    )
    assert wrong_actor.status_code == 200
    assert "capture token belongs to a different operator" in wrong_actor.content.decode().lower()
    assert EvidenceSnapshotManifest.objects.count() == 0


def test_export_queue_paginates_and_uses_bounded_queries(
    client, django_assert_max_num_queries
) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Export Pagination")
    actor = _actor(
        "export-page",
        organization,
        PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER,
        PrivilegedRoleAssignment.Role.EXPORT_REVIEWER,
    )
    for index in range(101):
        assertion = _assertion(organization, actor, f"export-page-{index:03}")
        review_export_eligibility(
            actor=actor,
            organization=organization,
            career_assertion=assertion,
            decision=ExportEligibilityRevision.Decision.ELIGIBLE,
            reason="Synthetic complete row",
            operator_key=f"export-page-review-{index:03}",
        )
    force_login_with_fresh_mfa(client, actor)

    # Includes fresh account, verified-email, and real-authenticator checks at
    # both the HTTP and service authorization boundaries.
    with django_assert_max_num_queries(18):
        first = client.get(reverse("export:review-queue"))
    assert first.status_code == 200
    first_body = first.content.decode()
    assert "Page 1 of 2" in first_body
    assert "Synthetic Event export-page-100" in first_body
    assert "Synthetic Event export-page-000" not in first_body

    second = client.get(reverse("export:review-queue"), {"page": 2})
    assert second.status_code == 200
    second_body = second.content.decode()
    assert "Page 2 of 2" in second_body
    assert "Synthetic Event export-page-000" in second_body


def test_snapshot_exclusions_are_paginated_and_downloadable_without_pii(client) -> None:
    organization = PartnerOrganization.objects.create(name="Synthetic Exclusion Operations")
    actor = _actor("exclusion-ops", organization, PrivilegedRoleAssignment.Role.EXPORT_REVIEWER)
    exclusions = [
        {
            "assertion_revision_id": str(uuid.UUID(int=index + 1)),
            "published_result_id": str(uuid.UUID(int=index + 1000)),
            "reason": "unreviewed",
        }
        for index in range(101)
    ]
    snapshot = EvidenceSnapshotManifest.objects.create(
        organization=organization,
        source_id="mnemex:snapshot:exclusion-ops",
        cutoff=datetime(2026, 8, 2, tzinfo=UTC).date(),
        captured_at=datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
        rows=[],
        exclusions=exclusions,
        source_digest="0" * 64,
        request_digest="1" * 64,
        reviewed_by=actor,
    )
    force_login_with_fresh_mfa(client, actor)

    first = client.get(reverse("export:snapshot-detail", args=[snapshot.pk]))
    first_body = first.content.decode()
    assert first.status_code == 200
    assert "Exclusions page 1 of 2" in first_body
    assert exclusions[0]["assertion_revision_id"] in first_body
    assert exclusions[100]["assertion_revision_id"] not in first_body
    second = client.get(
        reverse("export:snapshot-detail", args=[snapshot.pk]), {"exclusions_page": 2}
    )
    assert "Exclusions page 2 of 2" in second.content.decode()
    assert exclusions[100]["assertion_revision_id"] in second.content.decode()

    download = client.get(reverse("export:snapshot-exclusions-download", args=[snapshot.pk]))
    assert download.status_code == 200
    assert download["Content-Type"].startswith("text/csv")
    assert "attachment" in download["Content-Disposition"]
    assert download["X-Content-Type-Options"] == "nosniff"
    records = list(DictReader(StringIO(download.content.decode())))
    assert len(records) == 101
    assert set(records[0]) == {"assertion_revision_id", "reason"}
    assert {record["reason"] for record in records} == {"unreviewed"}
    assert "published_result_id" not in download.content.decode()
