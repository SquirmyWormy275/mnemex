from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from io import StringIO

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.core.management.base import CommandError
from django.db import connection
from django.test import override_settings

from mnemex.activation.checks import production_privilege_must_remain_disabled
from mnemex.activation.management.commands.activation_report import Command
from mnemex.activation.models import ActivationEvidence
from mnemex.activation.report import (
    ACTIVATION_GATES,
    ActivationReportError,
    build_activation_report,
    canonical_report_json,
    compute_environment_fingerprint,
    evidence_payload_digest,
    select_latest_evidence,
    verify_signed_report,
)

UTC = datetime_timezone.utc
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
ENVIRONMENT_FINGERPRINT = compute_environment_fingerprint(
    environment="local",
    release_digest="a" * 64,
    configuration_digest="b" * 64,
)


@pytest.fixture
def activation_evidence_table(transactional_db):
    """Provide the table until the activation app is wired into INSTALLED_APPS."""

    table_name = ActivationEvidence._meta.db_table
    created_here = table_name not in connection.introspection.table_names()
    if created_here:
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(ActivationEvidence)
    yield
    if created_here:
        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(ActivationEvidence)


def make_evidence(
    gate_id: str,
    *,
    result: str = ActivationEvidence.Result.PASS,
    environment_fingerprint: str = ENVIRONMENT_FINGERPRINT,
    evidence_time: datetime = NOW,
    expires_at: datetime | None = None,
    summary_code: str | None = None,
) -> ActivationEvidence:
    gate = ACTIVATION_GATES[gate_id]
    evidence = ActivationEvidence(
        gate_id=gate_id,
        result=result,
        source=gate.evidence_source,
        environment_fingerprint=environment_fingerprint,
        evidence_time=evidence_time,
        expires_at=expires_at or evidence_time + gate.freshness,
        summary_code=summary_code or f"evidence.{result}",
    )
    evidence.payload_digest = evidence_payload_digest(evidence)
    return evidence


def complete_evidence(*, environment_fingerprint: str = ENVIRONMENT_FINGERPRINT):
    return [
        make_evidence(gate_id, environment_fingerprint=environment_fingerprint)
        for gate_id in ACTIVATION_GATES
    ]


def test_closed_registry_traces_every_requirement_and_acceptance_example():
    requirements = {item for gate in ACTIVATION_GATES.values() for item in gate.requirements}
    examples = {item for gate in ACTIVATION_GATES.values() for item in gate.acceptance_examples}

    assert requirements == {f"R{number}" for number in range(1, 23)}
    assert examples == {f"AE{number}" for number in range(1, 13)}
    assert tuple(ACTIVATION_GATES) == tuple(sorted(ACTIVATION_GATES))
    assert all(gate.freshness > timedelta(0) for gate in ACTIVATION_GATES.values())


def test_environment_fingerprint_is_deterministic_and_accepts_only_digests():
    assert ENVIRONMENT_FINGERPRINT == compute_environment_fingerprint(
        environment="local",
        release_digest="A" * 64,
        configuration_digest="B" * 64,
    )

    with pytest.raises(ValueError, match="release_digest"):
        compute_environment_fingerprint(
            environment="local",
            release_digest="https://host.example/secret",
            configuration_digest="b" * 64,
        )


@pytest.mark.django_db(transaction=True)
def test_evidence_is_persisted_immutably(activation_evidence_table):
    evidence = make_evidence("G01_HOSTED_CONFIGURATION")
    evidence.save()

    evidence.summary_code = "changed"
    with pytest.raises(PermissionDenied, match="append-only"):
        evidence.save()
    with pytest.raises(PermissionDenied, match="append-only"):
        ActivationEvidence.objects.filter(pk=evidence.pk).update(summary_code="changed")
    with pytest.raises(PermissionDenied, match="append-only"):
        evidence.delete()


@pytest.mark.django_db(transaction=True)
def test_evidence_bulk_writes_cannot_bypass_append_only_validation(
    activation_evidence_table,
):
    evidence = make_evidence("G01_HOSTED_CONFIGURATION")

    with pytest.raises(PermissionDenied, match="append-only"):
        ActivationEvidence.objects.bulk_create([evidence])

    evidence.save()
    evidence.summary_code = "changed"
    with pytest.raises(PermissionDenied, match="append-only"):
        ActivationEvidence.objects.bulk_update([evidence], ["summary_code"])


@pytest.mark.django_db(transaction=True)
def test_evidence_rejects_unknown_gate_and_non_redacted_summary(activation_evidence_table):
    unknown = make_evidence("G01_HOSTED_CONFIGURATION")
    unknown.gate_id = "G99_UNKNOWN"
    with pytest.raises(ValidationError):
        unknown.save()

    unsafe = make_evidence(
        "G01_HOSTED_CONFIGURATION",
        summary_code="sent to operator@example.com",
    )
    with pytest.raises(ValidationError):
        unsafe.save()

    tampered = make_evidence("G01_HOSTED_CONFIGURATION")
    tampered.payload_digest = "0" * 64
    with pytest.raises(ValidationError):
        tampered.save()


def test_report_is_deterministic_redacted_and_keeps_hosted_gates_pending_locally():
    report = build_activation_report(
        complete_evidence(),
        environment="local",
        environment_fingerprint=ENVIRONMENT_FINGERPRINT,
        generated_at=NOW,
    )

    rendered = canonical_report_json(report)
    assert rendered == canonical_report_json(report)
    assert "operator@example.com" not in rendered
    assert "hostname" not in rendered
    assert report["decision"] == "blocked"
    assert report["production_privilege"] == "hard_disabled"
    assert any(gate["reason"] == "hosted_evidence_required" for gate in report["gates"])
    assert all(
        gate["result"] == "pending"
        for gate in report["gates"]
        if ACTIVATION_GATES[gate["gate_id"]].hosted_only
    )


def test_report_represents_missing_stale_and_failed_evidence_as_unsatisfied():
    gate_ids = list(ACTIVATION_GATES)
    stale = make_evidence(
        gate_ids[0],
        evidence_time=NOW - timedelta(days=2),
        expires_at=NOW - timedelta(days=1),
    )
    failed = make_evidence(gate_ids[1], result=ActivationEvidence.Result.FAIL)

    report = build_activation_report(
        [stale, failed],
        environment="staging",
        environment_fingerprint=ENVIRONMENT_FINGERPRINT,
        generated_at=NOW,
    )
    gates = {gate["gate_id"]: gate for gate in report["gates"]}

    assert gates[gate_ids[0]]["result"] == "pending"
    assert gates[gate_ids[0]]["reason"] == "stale"
    assert gates[gate_ids[1]]["result"] == "fail"
    assert gates[gate_ids[2]]["result"] == "pending"
    assert gates[gate_ids[2]]["reason"] == "missing"
    assert report["decision"] == "blocked"


@pytest.mark.parametrize("problem", ["duplicate", "tampered", "wrong_environment"])
def test_report_rejects_malformed_evidence_bundles(problem: str):
    evidence = make_evidence("G01_HOSTED_CONFIGURATION")
    records = [evidence]
    if problem == "duplicate":
        records.append(make_evidence("G01_HOSTED_CONFIGURATION"))
    elif problem == "tampered":
        evidence.payload_digest = "0" * 64
    else:
        evidence.environment_fingerprint = "c" * 64

    with pytest.raises(ActivationReportError, match=problem.replace("_", " ")):
        build_activation_report(
            records,
            environment="staging",
            environment_fingerprint=ENVIRONMENT_FINGERPRINT,
            generated_at=NOW,
        )


def test_report_rejects_unknown_evidence_gate():
    evidence = make_evidence("G01_HOSTED_CONFIGURATION")
    evidence.gate_id = "G99_UNKNOWN"

    with pytest.raises(ActivationReportError, match="unknown gate"):
        build_activation_report(
            [evidence],
            environment="staging",
            environment_fingerprint=ENVIRONMENT_FINGERPRINT,
            generated_at=NOW,
        )


def test_select_latest_evidence_produces_one_record_per_gate():
    older = make_evidence("G01_HOSTED_CONFIGURATION", evidence_time=NOW - timedelta(hours=1))
    newer = make_evidence("G01_HOSTED_CONFIGURATION", evidence_time=NOW)

    assert select_latest_evidence([newer, older]) == [newer]


def test_select_latest_evidence_rejects_conflicting_same_time_outcomes():
    passed = make_evidence("G01_HOSTED_CONFIGURATION")
    failed = make_evidence(
        "G01_HOSTED_CONFIGURATION",
        result=ActivationEvidence.Result.FAIL,
    )

    with pytest.raises(ActivationReportError, match="conflicting simultaneous evidence"):
        select_latest_evidence([passed, failed])


def test_valid_offline_signature_is_accepted_without_an_application_signing_api():
    hosted_fingerprint = compute_environment_fingerprint(
        environment="staging",
        release_digest="d" * 64,
        configuration_digest="e" * 64,
    )
    report = build_activation_report(
        complete_evidence(environment_fingerprint=hosted_fingerprint),
        environment="staging",
        environment_fingerprint=hosted_fingerprint,
        generated_at=NOW,
    )
    assert report["decision"] == "eligible_for_owner_review"

    private_key = Ed25519PrivateKey.generate()
    signature = private_key.sign(canonical_report_json(report).encode("ascii"))
    bundle = {
        "report": report,
        "signature": {
            "algorithm": "Ed25519",
            "key_id": "owner-2026",
            "value": base64.b64encode(signature).decode("ascii"),
        },
    }

    verified = verify_signed_report(
        bundle,
        public_key=private_key.public_key().public_bytes_raw(),
        expected_environment_fingerprint=hosted_fingerprint,
        verified_at=NOW,
    )
    assert verified == report


@pytest.mark.parametrize("mutation", ["unsigned", "invalid_signature", "wrong_environment"])
def test_offline_signature_verification_rejects_invalid_bundles(mutation: str):
    hosted_fingerprint = compute_environment_fingerprint(
        environment="production",
        release_digest="d" * 64,
        configuration_digest="e" * 64,
    )
    report = build_activation_report(
        complete_evidence(environment_fingerprint=hosted_fingerprint),
        environment="production",
        environment_fingerprint=hosted_fingerprint,
        generated_at=NOW,
    )
    private_key = Ed25519PrivateKey.generate()
    signature = private_key.sign(canonical_report_json(report).encode("ascii"))
    bundle = {
        "report": report,
        "signature": {
            "algorithm": "Ed25519",
            "key_id": "owner-2026",
            "value": base64.b64encode(signature).decode("ascii"),
        },
    }
    if mutation == "unsigned":
        bundle.pop("signature")
    elif mutation == "invalid_signature":
        bundle["report"]["decision"] = "activated"
    else:
        hosted_fingerprint = "f" * 64

    with pytest.raises(ActivationReportError):
        verify_signed_report(
            bundle,
            public_key=private_key.public_key().public_bytes_raw(),
            expected_environment_fingerprint=hosted_fingerprint,
            verified_at=NOW,
        )


def test_valid_signature_cannot_bless_extra_sensitive_report_fields():
    hosted_fingerprint = compute_environment_fingerprint(
        environment="staging",
        release_digest="d" * 64,
        configuration_digest="e" * 64,
    )
    report = build_activation_report(
        complete_evidence(environment_fingerprint=hosted_fingerprint),
        environment="staging",
        environment_fingerprint=hosted_fingerprint,
        generated_at=NOW,
    )
    report["gates"][0]["operator_email"] = "operator@example.com"
    private_key = Ed25519PrivateKey.generate()
    signature = private_key.sign(canonical_report_json(report).encode("ascii"))
    bundle = {
        "report": report,
        "signature": {
            "algorithm": "Ed25519",
            "key_id": "owner-2026",
            "value": base64.b64encode(signature).decode("ascii"),
        },
    }

    with pytest.raises(ActivationReportError, match="gate fields"):
        verify_signed_report(
            bundle,
            public_key=private_key.public_key().public_bytes_raw(),
            expected_environment_fingerprint=hosted_fingerprint,
            verified_at=NOW,
        )


def test_production_check_fails_closed_and_report_api_cannot_change_setting():
    with override_settings(
        SETTINGS_MODULE="mnemex.web.settings.production",
        MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED=True,
    ):
        errors = production_privilege_must_remain_disabled(None)
        assert errors and errors[0].id == "mnemex.activation.E001"

    with override_settings(MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED=False):
        build_activation_report(
            [],
            environment="local",
            environment_fingerprint=ENVIRONMENT_FINGERPRINT,
            generated_at=NOW,
        )
        assert settings.MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED is False


@pytest.mark.django_db(transaction=True)
def test_management_command_emits_diagnostic_json_without_mutating_privilege(
    activation_evidence_table,
):
    output = StringIO()
    command = Command(stdout=output)

    with override_settings(MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED=False):
        command.handle(
            environment="local",
            release_digest="a" * 64,
            configuration_digest="b" * 64,
            output_format="json",
        )
        assert settings.MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED is False

    report = json.loads(output.getvalue())
    assert report["decision"] == "blocked"
    assert report["production_privilege"] == "hard_disabled"
    assert len(report["gates"]) == len(ACTIVATION_GATES)


@pytest.mark.django_db(transaction=True)
def test_management_command_refuses_missing_historical_encryption_key(
    activation_evidence_table,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_key_check(*, purpose: str) -> None:
        raise ImproperlyConfigured(f"required {purpose} encryption key is unavailable")

    monkeypatch.setattr(
        "mnemex.activation.management.commands.activation_report."
        "assert_configured_key_versions_available",
        fail_key_check,
    )

    with pytest.raises(CommandError, match="required encryption key is unavailable"):
        Command(stdout=StringIO()).handle(
            environment="local",
            release_digest="a" * 64,
            configuration_digest="b" * 64,
            output_format="json",
        )
