"""Narrow source-attributed show inbox; no live provider or private records."""

import pytest
from django.test import override_settings

from mnemex.partners.models import PartnerClient, PartnerOrganization, ShowSource
from mnemex.partners.show_results import ShowResultError, receive_show_result


def envelope(revision=1, status="finished"):
    source = {
        "schema_version": "strathmark.source-result.v1",
        "source_show_id": "synthetic:missoula",
        "source_event_id": "synthetic:event",
        "source_result_id": "synthetic:event:q1:e0",
        "source_revision": revision,
        "heat_id": "q1",
        "field_digest": "f" * 64,
        "issue_id": "a" * 64,
        "discipline": "UH",
        "event_date": "2026-10-15",
        "wood": {"species": "S01", "diameter_mm": 275, "quality": None},
        "outcome": {
            "entry_id": "e0",
            "status": status,
            "timer1_seconds": "21.1",
            "timer2_seconds": "21.3",
            "raw_duration_seconds": "21.2",
            "start_mark_seconds": 3,
            "common_count_seconds": "24.2",
            "official_position": 1,
        },
        "result_digest": "b" * 64,
        "synthetic": True,
    }
    from mnemex.partners.show_results import digest

    source["supersedes_source_digest"] = (
        envelope(revision - 1)["source_digest"] if revision > 1 else None
    )
    source["correction_reason"] = "Synthetic result correction" if revision > 1 else None

    return {
        "schema_version": "mnemex.show-result.v1",
        "message_id": f"delivery-{revision}",
        "source": source,
        "source_digest": digest(source),
        "participant": {
            "show_person_ref": None,
            "unresolved_ref": "pro:1",
            "authorization_basis_ref": None,
        },
    }


@pytest.mark.django_db
@override_settings(MNEMEX_SHOW_RESULTS_ENABLED=True)
def test_reordered_duplicate_conflicting_and_unlinked_source_results():
    from mnemex.partners.models import ShowResultInbox, ShowResultStream

    org = PartnerOrganization.objects.create(name="Synthetic Missoula")
    client = PartnerClient.objects.create(organization=org, name="show", environment="sandbox")
    ShowSource.objects.create(client=client, source_show_id="synthetic:missoula")
    future = receive_show_result(client, "synthetic:missoula", envelope(2))
    assert future["state"] == "pending_predecessor"
    assert ShowResultStream.objects.get().current_revision == 0
    first = receive_show_result(client, "synthetic:missoula", envelope(1))
    assert first["state"] == "unlinked"
    assert receive_show_result(client, "synthetic:missoula", envelope(1)) == first
    assert ShowResultInbox.objects.count() == 2
    assert ShowResultStream.objects.get().current_revision == 2
    changed = envelope(1)
    changed["participant"]["unresolved_ref"] = "pro:2"
    assert receive_show_result(client, "synthetic:missoula", changed)["state"] == "conflicting"
    with pytest.raises(ShowResultError, match="source_show"):
        receive_show_result(client, "synthetic:other", envelope(3))


@pytest.mark.django_db
def test_disabled_receiver_cannot_be_enabled_by_payload():
    org = PartnerOrganization.objects.create(name="Synthetic show")
    client = PartnerClient.objects.create(organization=org, name="show", environment="sandbox")
    with pytest.raises(ShowResultError, match="disabled"):
        receive_show_result(client, "synthetic:missoula", envelope())


@pytest.mark.django_db
@override_settings(MNEMEX_SHOW_RESULTS_ENABLED=True)
def test_same_source_under_new_delivery_identity_keeps_original_receipt():
    from mnemex.partners.models import ShowResultInbox

    org = PartnerOrganization.objects.create(name="Synthetic delivery retry")
    client = PartnerClient.objects.create(organization=org, name="show", environment="sandbox")
    ShowSource.objects.create(client=client, source_show_id="synthetic:missoula")
    first = receive_show_result(client, "synthetic:missoula", envelope())
    retry = envelope()
    retry["message_id"] = "a-different-delivery"
    assert receive_show_result(client, "synthetic:missoula", retry) == first
    assert ShowResultInbox.objects.count() == 1


@pytest.mark.django_db
@override_settings(MNEMEX_SHOW_RESULTS_ENABLED=True)
def test_inbox_audit_receipt_and_projection_rollback_together(monkeypatch):
    from mnemex.foundation.models import IdempotencyRecord
    from mnemex.partners import show_results
    from mnemex.partners.models import ShowResultInbox, ShowResultStream

    org = PartnerOrganization.objects.create(name="Synthetic rollback")
    client = PartnerClient.objects.create(organization=org, name="show", environment="sandbox")
    ShowSource.objects.create(client=client, source_show_id="synthetic:missoula")

    def fail(**_kwargs):
        raise RuntimeError("synthetic precommit failure")

    monkeypatch.setattr(show_results, "record_audit_event", fail)
    with pytest.raises(RuntimeError, match="precommit"):
        receive_show_result(client, "synthetic:missoula", envelope())
    assert (
        ShowResultInbox.objects.count()
        == ShowResultStream.objects.count()
        == IdempotencyRecord.objects.count()
        == 0
    )


@pytest.mark.django_db
@override_settings(MNEMEX_SHOW_RESULTS_ENABLED=True)
def test_machine_endpoint_requires_scoped_current_credentials_and_rejects_pii():
    import hashlib
    import json
    from datetime import timedelta

    from django.test import Client as HttpClient
    from django.utils import timezone

    from mnemex.partners.models import ShowClientCredential, ShowResultInbox

    org = PartnerOrganization.objects.create(name="Synthetic endpoint")
    client = PartnerClient.objects.create(organization=org, name="show", environment="sandbox")
    ShowSource.objects.create(client=client, source_show_id="synthetic:missoula")
    token = "synthetic-test-service-token"
    credential = ShowClientCredential.objects.create(
        client=client,
        source_show_id="synthetic:missoula",
        token_sha256=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    http = HttpClient(enforce_csrf_checks=True)
    path = "/partners/results/ingest"
    assert (
        http.post(path, data=json.dumps(envelope()), content_type="application/json").status_code
        == 401
    )
    header = {"HTTP_AUTHORIZATION": "Bearer " + token}
    assert (
        http.post(
            path, data=json.dumps(envelope()), content_type="application/json", **header
        ).status_code
        == 200
    )
    contaminated = envelope(2)
    contaminated["source"]["outcome"]["email"] = "synthetic-private@example.invalid"
    assert (
        http.post(
            path, data=json.dumps(contaminated), content_type="application/json", **header
        ).status_code
        == 400
    )
    credential.revoked_at = timezone.now()
    credential.save(update_fields=("revoked_at",))
    assert (
        http.post(
            path, data=json.dumps(envelope(2)), content_type="application/json", **header
        ).status_code
        == 401
    )
    assert ShowResultInbox.objects.count() == 1


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("wood", "quality", -1),
        ("wood", "diameter_mm", "NaN"),
        ("outcome", "raw_duration_seconds", True),
        ("outcome", "official_position", 0),
        ("outcome", "timer2_seconds", "23"),
    ],
)
def test_malformed_source_facts_are_refused(section, key, value):
    from mnemex.partners.show_results import digest, validate

    payload = envelope()
    payload["source"][section][key] = value
    payload["source_digest"] = digest(payload["source"])
    with pytest.raises(ShowResultError):
        validate(payload, "synthetic:missoula")


@pytest.mark.django_db
@override_settings(MNEMEX_SHOW_RESULTS_ENABLED=True)
@pytest.mark.parametrize("binding", ["entry_id", "issue_id"])
def test_direct_invalid_correction_is_conflicting_without_poisoning_next_revision(binding):
    from mnemex.partners.models import ShowResultInbox, ShowResultStream
    from mnemex.partners.show_results import digest

    org = PartnerOrganization.objects.create(name="Synthetic correction binding")
    client = PartnerClient.objects.create(organization=org, name="show", environment="sandbox")
    ShowSource.objects.create(client=client, source_show_id="synthetic:missoula")
    receive_show_result(client, "synthetic:missoula", envelope())
    invalid = envelope(2)
    if binding == "entry_id":
        invalid["source"]["outcome"]["entry_id"] = "different-entry"
    else:
        invalid["source"]["issue_id"] = "c" * 64
    invalid["source_digest"] = digest(invalid["source"])
    rejected = receive_show_result(client, "synthetic:missoula", invalid)
    assert rejected["state"] == "conflicting"
    assert receive_show_result(client, "synthetic:missoula", invalid) == rejected
    assert ShowResultStream.objects.get().current_revision == 1
    assert ShowResultInbox.objects.count() == 1
    valid = envelope(2)
    valid["message_id"] = "valid-new-delivery"
    assert receive_show_result(client, "synthetic:missoula", valid)["state"] == "unlinked"
    assert ShowResultStream.objects.get().current_revision == 2


@pytest.mark.django_db
@override_settings(MNEMEX_SHOW_RESULTS_ENABLED=True)
def test_status_credential_cannot_count_another_shows_conflicts():
    import hashlib
    from datetime import timedelta

    from django.test import Client as HttpClient
    from django.utils import timezone

    from mnemex.partners.models import ShowClientCredential
    from mnemex.partners.show_results import digest

    org = PartnerOrganization.objects.create(name="Synthetic shared client")
    client = PartnerClient.objects.create(organization=org, name="two shows", environment="sandbox")
    for show in ("synthetic:missoula", "synthetic:other"):
        ShowSource.objects.create(client=client, source_show_id=show)
    token = "synthetic-scope-check-token"
    ShowClientCredential.objects.create(
        client=client,
        source_show_id="synthetic:missoula",
        token_sha256=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    other = envelope()
    other["message_id"] = "other-delivery"
    other["source"]["source_show_id"] = "synthetic:other"
    other["source_digest"] = digest(other["source"])
    receive_show_result(client, "synthetic:other", other)
    other["participant"]["unresolved_ref"] = "pro:2"
    assert receive_show_result(client, "synthetic:other", other)["state"] == "conflicting"
    response = HttpClient().post("/partners/results/status", HTTP_AUTHORIZATION="Bearer " + token)
    assert response.status_code == 200
    assert response.json()["stream_count"] == response.json()["conflict_count"] == 0
