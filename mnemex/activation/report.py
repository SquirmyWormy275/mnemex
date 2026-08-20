from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.utils import timezone as django_timezone

from .models import SAFE_SUMMARY_CODES, ActivationEvidence

HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
SAFE_KEY_ID = re.compile(r"^owner-[0-9]{4}(?:-[0-9]{2})?$")
HOSTED_ENVIRONMENTS = frozenset({"staging", "production"})
KNOWN_ENVIRONMENTS = frozenset({"local", *HOSTED_ENVIRONMENTS})


class ActivationReportError(ValueError):
    """The evidence or signed bundle cannot support an activation decision."""


@dataclass(frozen=True)
class GateDefinition:
    title: str
    requirements: tuple[str, ...]
    acceptance_examples: tuple[str, ...]
    evidence_source: str
    freshness: timedelta
    hosted_only: bool = False


# Closed, intentionally explicit registry. Any requirement addition must change this
# registry, its digest, and the acceptance tests together.
ACTIVATION_GATES: dict[str, GateDefinition] = {
    "G01_HOSTED_CONFIGURATION": GateDefinition(
        "Hosted configuration integrity",
        ("R1",),
        (),
        "hosted_configuration_check",
        timedelta(days=1),
        hosted_only=True,
    ),
    "G02_SHARED_AUTH_CONTROLS": GateDefinition(
        "Shared atomic authentication controls",
        ("R2", "R3"),
        ("AE1", "AE2"),
        "disposable_redis_test",
        timedelta(days=7),
    ),
    "G03_MFA_KEY_ROTATION": GateDefinition(
        "MFA key rotation and historical restore",
        ("R4",),
        ("AE6",),
        "synthetic_rotation_rehearsal",
        timedelta(days=30),
    ),
    "G04_SECURITY_NOTIFICATIONS": GateDefinition(
        "Durable security notifications",
        ("R5", "R9"),
        ("AE3",),
        "synthetic_mail_rehearsal",
        timedelta(days=7),
    ),
    "G05_PRIVILEGED_INVITATIONS": GateDefinition(
        "Privileged invitation controls",
        ("R6",),
        ("AE4",),
        "automated_acceptance_test",
        timedelta(days=7),
    ),
    "G06_STAFF_RECOVERY": GateDefinition(
        "Two-person staff recovery",
        ("R7", "R8"),
        ("AE5",),
        "synthetic_recovery_rehearsal",
        timedelta(days=30),
    ),
    "G07_PRIVATE_OBJECT_STORAGE": GateDefinition(
        "Private hosted object integrity",
        ("R10", "R11"),
        ("AE7",),
        "hosted_private_bucket_observation",
        timedelta(days=7),
        hosted_only=True,
    ),
    "G08_RAILWAY_RUNTIME": GateDefinition(
        "Railway release and process separation",
        ("R12", "R13"),
        ("AE8",),
        "hosted_release_observation",
        timedelta(days=7),
        hosted_only=True,
    ),
    "G09_HOSTED_MONITORING": GateDefinition(
        "Hosted operational monitoring",
        ("R14",),
        (),
        "hosted_monitoring_observation",
        timedelta(days=7),
        hosted_only=True,
    ),
    "G10_RECOVERY_REHEARSAL": GateDefinition(
        "Database, object, and key recovery",
        ("R15", "R16"),
        ("AE9",),
        "disposable_restore_rehearsal",
        timedelta(days=30),
    ),
    "G11_ACTIVATION_INTEGRITY": GateDefinition(
        "Signed fail-closed activation evidence",
        ("R17", "R18", "R19"),
        ("AE10",),
        "automated_activation_test",
        timedelta(days=7),
    ),
    "G12_AUTHORITY_BOUNDARY": GateDefinition(
        "Offline race-day authority boundary",
        ("R20",),
        (),
        "contract_review",
        timedelta(days=30),
    ),
    "G13_OPERATOR_STEP_UP": GateDefinition(
        "Non-replaying operator step-up",
        ("R21",),
        ("AE11",),
        "browser_acceptance_test",
        timedelta(days=7),
    ),
    "G14_FIRST_OPERATOR_REHEARSAL": GateDefinition(
        "First-time operator and approver rehearsal",
        ("R22",),
        ("AE12",),
        "independent_operator_observation",
        timedelta(days=30),
    ),
}


def _iso8601(value: datetime) -> str:
    if not django_timezone.is_aware(value):
        raise ActivationReportError("timestamps must include a timezone")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_iso8601(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise ActivationReportError(f"{field} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ActivationReportError(f"{field} is not valid ISO-8601") from exc
    if not django_timezone.is_aware(parsed):
        raise ActivationReportError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def canonical_report_json(report: Mapping[str, Any]) -> str:
    """Return the sole byte representation used for offline signatures."""

    return _canonical_bytes(report).decode("ascii")


def _registry_digest() -> str:
    registry = {
        gate_id: {
            "acceptance_examples": list(gate.acceptance_examples),
            "evidence_source": gate.evidence_source,
            "freshness_seconds": int(gate.freshness.total_seconds()),
            "hosted_only": gate.hosted_only,
            "requirements": list(gate.requirements),
            "title": gate.title,
        }
        for gate_id, gate in ACTIVATION_GATES.items()
    }
    return hashlib.sha256(_canonical_bytes(registry)).hexdigest()


REGISTRY_DIGEST = _registry_digest()


def compute_environment_fingerprint(
    *,
    environment: str,
    release_digest: str,
    configuration_digest: str,
) -> str:
    """Bind evidence without accepting a hostname, credential, or raw configuration."""

    normalized_environment = environment.strip().lower()
    if normalized_environment not in KNOWN_ENVIRONMENTS:
        raise ValueError("environment must be local, staging, or production")
    release_digest = release_digest.strip().lower()
    configuration_digest = configuration_digest.strip().lower()
    if not HEX_DIGEST.fullmatch(release_digest):
        raise ValueError("release_digest must be a SHA-256 hex digest")
    if not HEX_DIGEST.fullmatch(configuration_digest):
        raise ValueError("configuration_digest must be a SHA-256 hex digest")
    payload = {
        "configuration_digest": configuration_digest,
        "environment": normalized_environment,
        "release_digest": release_digest,
    }
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def evidence_payload_digest(evidence: ActivationEvidence) -> str:
    payload = {
        "environment_fingerprint": evidence.environment_fingerprint,
        "evidence_time": _iso8601(evidence.evidence_time),
        "expires_at": _iso8601(evidence.expires_at),
        "gate_id": evidence.gate_id,
        "result": evidence.result,
        "source": evidence.source,
        "summary_code": evidence.summary_code,
    }
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def select_latest_evidence(
    evidence_records: Iterable[ActivationEvidence],
) -> list[ActivationEvidence]:
    """Derive a unique current snapshot from append-only evidence history."""

    latest: dict[str, ActivationEvidence] = {}
    for evidence in evidence_records:
        if evidence.gate_id not in ACTIVATION_GATES:
            raise ActivationReportError(f"unknown gate: {evidence.gate_id}")
        existing = latest.get(evidence.gate_id)
        if existing is not None and evidence.evidence_time == existing.evidence_time:
            if not hmac.compare_digest(evidence.payload_digest, existing.payload_digest):
                raise ActivationReportError(
                    f"conflicting simultaneous evidence for gate {evidence.gate_id}"
                )
            continue
        if existing is None or evidence.evidence_time > existing.evidence_time:
            latest[evidence.gate_id] = evidence
    return [latest[gate_id] for gate_id in ACTIVATION_GATES if gate_id in latest]


def _validate_evidence(
    evidence_records: Sequence[ActivationEvidence],
    *,
    environment_fingerprint: str,
) -> dict[str, ActivationEvidence]:
    by_gate: dict[str, ActivationEvidence] = {}
    for evidence in evidence_records:
        gate = ACTIVATION_GATES.get(evidence.gate_id)
        if gate is None:
            raise ActivationReportError(f"unknown gate: {evidence.gate_id}")
        if evidence.gate_id in by_gate:
            raise ActivationReportError(f"duplicate evidence for gate {evidence.gate_id}")
        if evidence.environment_fingerprint != environment_fingerprint:
            raise ActivationReportError(f"wrong environment for gate {evidence.gate_id}")
        if evidence.source != gate.evidence_source:
            raise ActivationReportError(f"wrong evidence source for gate {evidence.gate_id}")
        if evidence.result not in ActivationEvidence.Result.values:
            raise ActivationReportError(f"invalid result for gate {evidence.gate_id}")
        if evidence.summary_code != f"evidence.{evidence.result}":
            raise ActivationReportError(f"unsafe summary code for gate {evidence.gate_id}")
        if evidence.expires_at <= evidence.evidence_time:
            raise ActivationReportError(f"invalid freshness for gate {evidence.gate_id}")
        if evidence.expires_at > evidence.evidence_time + gate.freshness:
            raise ActivationReportError(f"invalid freshness for gate {evidence.gate_id}")
        expected_digest = evidence_payload_digest(evidence)
        if not hmac.compare_digest(evidence.payload_digest, expected_digest):
            raise ActivationReportError(f"tampered evidence for gate {evidence.gate_id}")
        by_gate[evidence.gate_id] = evidence
    return by_gate


def build_activation_report(
    evidence_records: Sequence[ActivationEvidence],
    *,
    environment: str,
    environment_fingerprint: str,
    generated_at: datetime,
) -> dict[str, Any]:
    """Build a diagnostic decision artifact; this function grants no authority."""

    environment = environment.strip().lower()
    if environment not in KNOWN_ENVIRONMENTS:
        raise ActivationReportError("unknown environment")
    if not HEX_DIGEST.fullmatch(environment_fingerprint):
        raise ActivationReportError("environment fingerprint must be a SHA-256 digest")
    generated_at_text = _iso8601(generated_at)
    by_gate = _validate_evidence(
        evidence_records,
        environment_fingerprint=environment_fingerprint,
    )

    gate_results: list[dict[str, Any]] = []
    valid_until_values: list[datetime] = []
    for gate_id, gate in ACTIVATION_GATES.items():
        evidence = by_gate.get(gate_id)
        result = ActivationEvidence.Result.PENDING
        reason = "missing"
        source: str | None = None
        evidence_time: str | None = None
        expires_at: str | None = None
        summary_code: str | None = None
        if evidence is not None:
            source = evidence.source
            evidence_time = _iso8601(evidence.evidence_time)
            expires_at = _iso8601(evidence.expires_at)
            summary_code = evidence.summary_code
            if evidence.evidence_time > generated_at + timedelta(minutes=5):
                raise ActivationReportError(f"future evidence for gate {gate_id}")
            if gate.hosted_only and environment == "local":
                reason = "hosted_evidence_required"
            elif evidence.expires_at <= generated_at:
                reason = "stale"
            elif evidence.result == ActivationEvidence.Result.PASS:
                result = ActivationEvidence.Result.PASS
                reason = "satisfied"
                valid_until_values.append(evidence.expires_at)
            elif evidence.result == ActivationEvidence.Result.FAIL:
                result = ActivationEvidence.Result.FAIL
                reason = "evidence_failed"
            else:
                reason = "evidence_pending"
        gate_results.append(
            {
                "acceptance_examples": list(gate.acceptance_examples),
                "evidence_time": evidence_time,
                "expires_at": expires_at,
                "gate_id": gate_id,
                "reason": reason,
                "requirements": list(gate.requirements),
                "result": str(result),
                "source": source,
                "summary_code": summary_code,
                "title": gate.title,
            }
        )

    all_pass = all(item["result"] == ActivationEvidence.Result.PASS for item in gate_results)
    return {
        "decision": "eligible_for_owner_review" if all_pass else "blocked",
        "environment": environment,
        "environment_fingerprint": environment_fingerprint,
        "gates": gate_results,
        "generated_at": generated_at_text,
        "production_privilege": "hard_disabled",
        "registry_digest": REGISTRY_DIGEST,
        "report_version": 1,
        "valid_until": _iso8601(min(valid_until_values)) if all_pass else None,
    }


def _load_public_key(value: bytes | str) -> Ed25519PublicKey:
    encoded = value.encode("ascii") if isinstance(value, str) else value
    if isinstance(value, str) and value.startswith("base64:"):
        try:
            encoded = base64.b64decode(value.removeprefix("base64:"), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ActivationReportError("invalid owner public key") from exc
    if len(encoded) == 32:
        try:
            return Ed25519PublicKey.from_public_bytes(encoded)
        except ValueError as exc:
            raise ActivationReportError("invalid owner public key") from exc
    try:
        loaded = serialization.load_pem_public_key(encoded)
    except (TypeError, ValueError) as exc:
        raise ActivationReportError("invalid owner public key") from exc
    if not isinstance(loaded, Ed25519PublicKey):
        raise ActivationReportError("owner public key must use Ed25519")
    return loaded


def _validate_verified_report(
    report: Mapping[str, Any],
    *,
    expected_environment_fingerprint: str,
    verified_at: datetime,
) -> None:
    expected_keys = {
        "decision",
        "environment",
        "environment_fingerprint",
        "gates",
        "generated_at",
        "production_privilege",
        "registry_digest",
        "report_version",
        "valid_until",
    }
    if set(report) != expected_keys:
        raise ActivationReportError("signed report fields do not match the closed schema")
    if report.get("report_version") != 1 or report.get("registry_digest") != REGISTRY_DIGEST:
        raise ActivationReportError("signed report registry is unknown")
    if report.get("environment") not in HOSTED_ENVIRONMENTS:
        raise ActivationReportError("final signed report must describe a hosted environment")
    if report.get("environment_fingerprint") != expected_environment_fingerprint:
        raise ActivationReportError("signed report has the wrong environment")
    if report.get("production_privilege") != "hard_disabled":
        raise ActivationReportError("signed report does not preserve the privilege boundary")
    if report.get("decision") != "eligible_for_owner_review":
        raise ActivationReportError("signed report is not eligible for owner review")
    if not HEX_DIGEST.fullmatch(expected_environment_fingerprint):
        raise ActivationReportError("expected environment fingerprint is invalid")
    if not django_timezone.is_aware(verified_at):
        raise ActivationReportError("verified_at must include a timezone")
    generated_at = _parse_iso8601(report.get("generated_at"), field="generated_at")
    verified_at = verified_at.astimezone(timezone.utc)
    if generated_at > verified_at + timedelta(minutes=5):
        raise ActivationReportError("signed report was generated in the future")
    valid_until = _parse_iso8601(report.get("valid_until"), field="valid_until")
    if valid_until <= verified_at:
        raise ActivationReportError("signed report is stale")

    gates = report.get("gates")
    if not isinstance(gates, list):
        raise ActivationReportError("signed report gates must be a list")
    gate_ids = [item.get("gate_id") for item in gates if isinstance(item, dict)]
    if len(gate_ids) != len(gates) or len(gate_ids) != len(set(gate_ids)):
        raise ActivationReportError("signed report contains duplicated gates")
    if gate_ids != list(ACTIVATION_GATES):
        raise ActivationReportError("signed report is missing or contains unknown gates")
    expected_gate_fields = {
        "acceptance_examples",
        "evidence_time",
        "expires_at",
        "gate_id",
        "reason",
        "requirements",
        "result",
        "source",
        "summary_code",
        "title",
    }
    expiries: list[datetime] = []
    for item in gates:
        if set(item) != expected_gate_fields:
            raise ActivationReportError("signed report gate fields do not match the closed schema")
        gate = ACTIVATION_GATES[item["gate_id"]]
        if (
            item.get("acceptance_examples") != list(gate.acceptance_examples)
            or item.get("requirements") != list(gate.requirements)
            or item.get("title") != gate.title
            or item.get("source") != gate.evidence_source
        ):
            raise ActivationReportError("signed report gate metadata does not match the registry")
        if (
            item.get("result") != ActivationEvidence.Result.PASS
            or item.get("reason") != "satisfied"
        ):
            raise ActivationReportError("signed report contains an unsatisfied gate")
        summary_code = item.get("summary_code")
        if summary_code not in SAFE_SUMMARY_CODES or summary_code != f"evidence.{item['result']}":
            raise ActivationReportError("signed report contains an unsafe summary code")
        evidence_time = _parse_iso8601(
            item.get("evidence_time"), field=f"{item['gate_id']}.evidence_time"
        )
        expiry = _parse_iso8601(item.get("expires_at"), field=f"{item['gate_id']}.expires_at")
        if evidence_time > generated_at + timedelta(minutes=5):
            raise ActivationReportError("signed report contains future evidence")
        if expiry <= verified_at or expiry > evidence_time + gate.freshness:
            raise ActivationReportError("signed report contains invalid gate freshness")
        expiries.append(expiry)
    if valid_until != min(expiries):
        raise ActivationReportError("signed report valid_until does not match gate evidence")


def verify_signed_report(
    bundle: Mapping[str, Any],
    *,
    public_key: bytes | str,
    expected_environment_fingerprint: str,
    verified_at: datetime,
) -> Mapping[str, Any]:
    """Verify an offline owner signature. MNEMEX intentionally has no signing API."""

    if set(bundle) != {"report", "signature"}:
        raise ActivationReportError("signed bundle must contain one report and signature")
    report = bundle.get("report")
    signature = bundle.get("signature")
    if not isinstance(report, dict) or not isinstance(signature, dict):
        raise ActivationReportError("signed bundle is malformed")
    if set(signature) != {"algorithm", "key_id", "value"}:
        raise ActivationReportError("signature fields do not match the closed schema")
    if signature.get("algorithm") != "Ed25519":
        raise ActivationReportError("signature algorithm must be Ed25519")
    key_id = signature.get("key_id")
    if not isinstance(key_id, str) or not SAFE_KEY_ID.fullmatch(key_id):
        raise ActivationReportError("signature key_id is invalid")
    try:
        signature_bytes = base64.b64decode(signature.get("value", ""), validate=True)
    except (binascii.Error, ValueError, TypeError) as exc:
        raise ActivationReportError("signature value is invalid") from exc
    try:
        _load_public_key(public_key).verify(signature_bytes, _canonical_bytes(report))
    except InvalidSignature as exc:
        raise ActivationReportError("offline owner signature is invalid") from exc
    _validate_verified_report(
        report,
        expected_environment_fingerprint=expected_environment_fingerprint,
        verified_at=verified_at,
    )
    return report
