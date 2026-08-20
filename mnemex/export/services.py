from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from datetime import timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Subquery
from django.utils import timezone

from mnemex.accounts.authorization import Action, may_perform
from mnemex.accounts.models import Account
from mnemex.career.models import CareerAssertionRevision
from mnemex.export.contract import (
    EVIDENCE_HISTORY_ROW_SCHEMA_VERSION,
    EVIDENCE_SNAPSHOT_SOURCE_SCHEMA_VERSION,
    SPECIES_CODE,
    STRATHMARK_EXPORT_DISCIPLINE_MAP,
    STRATHMARK_MAX_EVIDENCE_ROWS,
    STRATHMARK_MAX_EVIDENCE_SOURCE_BYTES,
    canonical_source_digest,
    pseudonymous_id,
    validate_namespaced_id,
)
from mnemex.export.models import EvidenceSnapshotManifest, ExportEligibilityRevision
from mnemex.foundation.models import IdempotencyRecord
from mnemex.foundation.services import (
    IdempotencyConflict,
    claim_idempotency,
    record_audit_event,
)
from mnemex.partners.models import PartnerOrganization
from mnemex.results.models import PublishedSourceResult
from mnemex.schema import ScoreType

MAX_EVIDENCE_ROWS = STRATHMARK_MAX_EVIDENCE_ROWS
MAX_EVIDENCE_SOURCE_BYTES = STRATHMARK_MAX_EVIDENCE_SOURCE_BYTES
MAX_SNAPSHOT_CANDIDATES = STRATHMARK_MAX_EVIDENCE_ROWS
MAX_SNAPSHOT_MANIFEST_BYTES = STRATHMARK_MAX_EVIDENCE_SOURCE_BYTES


@dataclass(frozen=True)
class ExportEligibilityOutcome:
    revision: ExportEligibilityRevision
    replayed: bool


@dataclass(frozen=True)
class EvidenceSnapshotOutcome:
    snapshot: EvidenceSnapshotManifest
    replayed: bool


def _digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_size(value: object) -> int:
    return len(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
        ).encode("utf-8")
    )


def _authorize(actor: Account, organization: PartnerOrganization) -> None:
    if not may_perform(actor, Action.REVIEW_EXPORT, organization=organization):
        raise PermissionDenied(
            "an MFA-bound export reviewer role for this organization is required"
        )


def _active_organization(organization: PartnerOrganization) -> PartnerOrganization:
    current = PartnerOrganization.objects.select_for_update().filter(pk=organization.pk).first()
    if current is None or current.status != PartnerOrganization.Status.ACTIVE:
        raise ValidationError("export organization is not active")
    return current


def _text(value: str, label: str, *, maximum: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValidationError(f"{label} must contain 1 to {maximum} characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ValidationError(f"{label} cannot contain control characters")
    return normalized


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _validated_source_fields(
    assertion: CareerAssertionRevision,
) -> tuple[dict[str, Any] | None, str | None]:
    source = assertion.source_result
    payload = source.normalized_payload
    if not isinstance(payload, dict):
        return None, "invalid_source_payload"
    event_code = STRATHMARK_EXPORT_DISCIPLINE_MAP.get(source.discipline)
    if event_code is None:
        return None, "unsupported_discipline"
    if source.score_type != ScoreType.TIME.value:
        return None, "unsupported_score_type"
    score_raw = payload.get("score")
    if isinstance(score_raw, bool):
        return None, "invalid_score_number"
    try:
        score_decimal = Decimal(str(score_raw))
    except (InvalidOperation, TypeError, ValueError):
        return None, "invalid_score_number"
    if not score_decimal.is_finite():
        return None, "invalid_score_nonfinite"
    if not Decimal(3) <= score_decimal <= Decimal(180):
        return None, "invalid_score_range"
    score = float(score_decimal)
    result_raw = payload.get("result_date")
    if not result_raw:
        return None, "missing_result_date"
    try:
        result_date = date.fromisoformat(str(result_raw))
    except ValueError:
        return None, "invalid_result_date"
    species = str(payload.get("wood_species") or "").strip()
    diameter_raw = payload.get("wood_diameter_mm")
    quality_raw = payload.get("wood_quality")
    if not species or diameter_raw in (None, "") or quality_raw in (None, ""):
        return None, "missing_wood_metadata"
    if not SPECIES_CODE.fullmatch(species):
        return None, "invalid_species"
    try:
        if isinstance(diameter_raw, bool) or float(str(diameter_raw)) != int(str(diameter_raw)):
            raise ValueError
        diameter = int(str(diameter_raw))
    except (TypeError, ValueError, OverflowError):
        return None, "invalid_diameter"
    if not 225 <= diameter <= 500:
        return None, "invalid_diameter"
    try:
        if isinstance(quality_raw, bool) or float(str(quality_raw)) != int(str(quality_raw)):
            raise ValueError
        quality = int(str(quality_raw))
    except (TypeError, ValueError, OverflowError):
        return None, "invalid_quality"
    if not 1 <= quality <= 10:
        return None, "invalid_quality"
    event_source = str(payload.get("source_event_id") or "").strip()
    if not event_source:
        return None, "missing_source_event_id"
    return (
        {
            "diameter": diameter,
            "event_code": event_code,
            "event_source": event_source,
            "heat_source": str(payload.get("heat_id") or "").strip(),
            "quality": quality,
            "result_date": result_date,
            "score": score,
            "species": species,
        },
        None,
    )


_ELIGIBILITY_ERROR_MESSAGES = {
    "invalid_source_payload": "current assertion source payload is invalid",
    "unsupported_discipline": "current assertion uses an unsupported discipline; only Standing Block or Underhand is eligible",
    "unsupported_score_type": "current assertion must be time-scored",
    "invalid_score_number": "current assertion score must be a number",
    "invalid_score_nonfinite": "current assertion score must be finite",
    "invalid_score_range": "current assertion score must be between 3 and 180 seconds",
    "missing_result_date": "current assertion must include a result date",
    "invalid_result_date": "current assertion result date must be a valid ISO date",
    "missing_wood_metadata": "current assertion must include species, diameter, and quality",
    "invalid_species": "current assertion species must be a STRATHMARK-safe code",
    "invalid_diameter": "current assertion diameter must be an integer from 225 to 500 millimeters",
    "invalid_quality": "current assertion quality must be an integer from 1 to 10",
    "missing_source_event_id": "current assertion must include a source event ID",
}


def _validate_eligible_assertion(assertion: CareerAssertionRevision) -> None:
    fields, reason = _validated_source_fields(assertion)
    if reason is not None:
        raise ValidationError(_ELIGIBILITY_ERROR_MESSAGES[reason])
    if fields is None:
        raise ValidationError("current assertion is not exportable")
    if fields["result_date"] > timezone.now().astimezone(dt_timezone.utc).date():
        raise ValidationError("current assertion result date cannot be in the future")


def _eligibility_replay(record: IdempotencyRecord) -> ExportEligibilityOutcome | None:
    if record.status != IdempotencyRecord.Status.COMPLETED or not isinstance(record.response, dict):
        return None
    revision_id = record.response.get("eligibility_revision_id")
    if not isinstance(revision_id, str):
        return None
    revision = ExportEligibilityRevision.objects.filter(pk=revision_id).first()
    return ExportEligibilityOutcome(revision, True) if revision is not None else None


@transaction.atomic
def review_export_eligibility(
    *,
    actor: Account,
    organization: PartnerOrganization,
    career_assertion: CareerAssertionRevision,
    decision: ExportEligibilityRevision.Decision | str,
    reason: str,
    operator_key: str,
) -> ExportEligibilityOutcome:
    _authorize(actor, organization)
    current_organization = _active_organization(organization)
    normalized_decision = _enum_value(decision)
    if normalized_decision not in ExportEligibilityRevision.Decision.values:
        raise ValidationError("export eligibility decision is not recognized")
    normalized_reason = _text(reason, "review reason", maximum=240)
    normalized_key = _text(operator_key, "operator key", maximum=200)
    assertion = (
        CareerAssertionRevision.objects.select_for_update()
        .select_related("source_result")
        .filter(pk=career_assertion.pk)
        .first()
    )
    if assertion is None:
        raise ValidationError("career assertion does not exist")
    if assertion.organization_id != current_organization.pk:
        raise PermissionDenied("career assertion is outside the requested organization scope")
    if CareerAssertionRevision.objects.filter(predecessor_id=assertion.pk).exists():
        raise ValidationError("only a current career assertion may receive an export review")
    if PublishedSourceResult.objects.filter(predecessor_id=assertion.source_result_id).exists():
        raise ValidationError("only the latest source result revision may receive an export review")
    if normalized_decision == ExportEligibilityRevision.Decision.ELIGIBLE:
        _validate_eligible_assertion(assertion)
    request_digest = _digest(
        {
            "actor_id": str(actor.pk),
            "assertion_revision_id": str(assertion.pk),
            "decision": normalized_decision,
            "organization_id": str(current_organization.pk),
            "reason": normalized_reason,
            "source_payload_digest": assertion.source_payload_digest,
        }
    )
    record, _ = claim_idempotency(
        scope=f"export-eligibility:{current_organization.pk}",
        key=normalized_key,
        request_digest=request_digest,
    )
    replay = _eligibility_replay(record)
    if replay is not None:
        return replay
    predecessor = (
        ExportEligibilityRevision.objects.select_for_update()
        .filter(career_assertion=assertion)
        .order_by("-revision")
        .first()
    )
    revision = ExportEligibilityRevision.objects.create(
        organization=current_organization,
        career_assertion=assertion,
        revision=1 if predecessor is None else predecessor.revision + 1,
        predecessor=predecessor,
        decision=normalized_decision,
        reason=normalized_reason,
        reviewed_by=actor,
        decision_digest=request_digest,
    )
    record.status = IdempotencyRecord.Status.COMPLETED
    record.response = {"eligibility_revision_id": str(revision.pk)}
    record.save(update_fields=["status", "response", "updated_at"])
    metadata = {
        "assertion_revision_id": str(assertion.pk),
        "decision": normalized_decision,
        "organization_id": str(current_organization.pk),
        "revision": revision.revision,
        "published_result_id": str(assertion.source_result_id),
    }
    if predecessor is not None:
        metadata["predecessor_eligibility_id"] = str(predecessor.pk)
    record_audit_event(
        actor_id=actor.pk,
        action="export.eligibility_reviewed",
        target_type="export_eligibility_revision",
        target_id=str(revision.pk),
        payload_digest=request_digest,
        metadata=metadata,
    )
    return ExportEligibilityOutcome(revision, False)


def _exclusion(assertion: CareerAssertionRevision, reason: str) -> dict[str, str]:
    return {
        "assertion_revision_id": str(assertion.pk),
        "published_result_id": str(assertion.source_result_id),
        "reason": reason,
    }


def _evidence_row(
    assertion: CareerAssertionRevision, *, cutoff: date, captured_at: datetime
) -> tuple[dict[str, Any] | None, str | None]:
    fields, reason = _validated_source_fields(assertion)
    if reason is not None:
        if reason.startswith("invalid_score_"):
            reason = "invalid_score"
        return None, reason
    if fields is None:
        return None, "invalid_source_payload"
    result_date = fields["result_date"]
    if result_date >= cutoff:
        return None, "on_or_after_cutoff"
    if result_date > captured_at.astimezone(dt_timezone.utc).date():
        return None, "after_capture"
    competition_id = pseudonymous_id("event", assertion.organization_id, fields["event_source"])
    heat_source = fields["heat_source"]
    heat_id = (
        pseudonymous_id(
            "heat",
            assertion.organization_id,
            fields["event_source"],
            heat_source,
        )
        if heat_source
        else ""
    )
    return (
        {
            "schema_version": EVIDENCE_HISTORY_ROW_SCHEMA_VERSION,
            "competitor_id": pseudonymous_id("competitor", "strathmark-v1", assertion.person_id),
            "event_code": fields["event_code"],
            "time_seconds": fields["score"],
            "species": fields["species"],
            "diameter_mm": fields["diameter"],
            "quality": fields["quality"],
            "competition_id": competition_id,
            "heat_id": heat_id,
            "result_date": result_date.isoformat(),
        },
        None,
    )


def _snapshot_replay(record: IdempotencyRecord) -> EvidenceSnapshotOutcome | None:
    if record.status != IdempotencyRecord.Status.COMPLETED or not isinstance(record.response, dict):
        return None
    snapshot_id = record.response.get("snapshot_id")
    if not isinstance(snapshot_id, str):
        return None
    snapshot = EvidenceSnapshotManifest.objects.filter(pk=snapshot_id).first()
    return EvidenceSnapshotOutcome(snapshot, True) if snapshot is not None else None


@transaction.atomic
def generate_evidence_snapshot(
    *,
    actor: Account,
    organization: PartnerOrganization,
    source_id: str,
    cutoff: date,
    captured_at: datetime,
    operator_key: str,
) -> EvidenceSnapshotOutcome:
    _authorize(actor, organization)
    current_organization = _active_organization(organization)
    normalized_source_id = validate_namespaced_id(source_id, "source_id")
    normalized_key = _text(operator_key, "operator key", maximum=200)
    if isinstance(cutoff, datetime) or not isinstance(cutoff, date):
        raise ValidationError("cutoff must be a date without a time")
    if captured_at.tzinfo is None:
        raise ValidationError("captured_at must be timezone-aware")
    captured_utc = captured_at.astimezone(dt_timezone.utc)
    if captured_utc > timezone.now().astimezone(dt_timezone.utc):
        raise ValidationError("captured_at cannot be in the future")

    latest_eligibility = ExportEligibilityRevision.objects.filter(
        career_assertion_id=OuterRef("pk"), created_at__lte=captured_utc
    ).order_by("-revision", "-eligibility_revision_id")
    assertion_query = (
        CareerAssertionRevision.objects.select_for_update()
        .select_related("source_result", "person")
        .filter(
            organization=current_organization,
            created_at__lte=captured_utc,
            source_result__published_at__lte=captured_utc,
        )
        .annotate(
            snapshot_has_identity_successor=Exists(
                CareerAssertionRevision.objects.filter(
                    predecessor_id=OuterRef("pk"), created_at__lte=captured_utc
                )
            ),
            snapshot_has_source_successor=Exists(
                PublishedSourceResult.objects.filter(
                    predecessor_id=OuterRef("source_result_id"),
                    published_at__lte=captured_utc,
                )
            ),
            snapshot_eligibility_decision=Subquery(latest_eligibility.values("decision")[:1]),
        )
        .order_by("source_result_id", "revision", "assertion_revision_id")
    )
    assertions = list(assertion_query[: MAX_SNAPSHOT_CANDIDATES + 1])
    if len(assertions) > MAX_SNAPSHOT_CANDIDATES:
        raise ValidationError(
            f"evidence snapshots may inspect at most {MAX_SNAPSHOT_CANDIDATES} candidate assertions"
        )
    rows: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    for assertion in assertions:
        if getattr(assertion, "snapshot_has_identity_successor", False):
            exclusions.append(_exclusion(assertion, "superseded_identity_assertion"))
            continue
        if getattr(assertion, "snapshot_has_source_successor", False):
            exclusions.append(_exclusion(assertion, "superseded_source_revision"))
            continue
        eligibility_decision = getattr(assertion, "snapshot_eligibility_decision", None)
        if eligibility_decision is None:
            exclusions.append(_exclusion(assertion, "unreviewed"))
            continue
        if eligibility_decision != ExportEligibilityRevision.Decision.ELIGIBLE:
            exclusions.append(_exclusion(assertion, "review_rejected"))
            continue
        row, reason = _evidence_row(assertion, cutoff=cutoff, captured_at=captured_utc)
        if reason is not None:
            exclusions.append(_exclusion(assertion, reason))
        elif row is not None:
            rows.append(row)
    rows.sort(
        key=lambda row: (
            row["competitor_id"],
            row["event_code"],
            row["result_date"],
            row["competition_id"],
            row["heat_id"],
            row["time_seconds"],
        )
    )
    exclusions.sort(key=lambda item: (item["assertion_revision_id"], item["reason"]))
    if len(rows) > MAX_EVIDENCE_ROWS:
        raise ValidationError(
            f"STRATHMARK evidence snapshots may contain at most {MAX_EVIDENCE_ROWS} rows"
        )
    try:
        source_digest = canonical_source_digest(
            source_id=normalized_source_id,
            cutoff=cutoff,
            captured_at=captured_utc,
            rows=rows,
            max_bytes=MAX_EVIDENCE_SOURCE_BYTES,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    manifest_size = _canonical_size(
        {
            "captured_at": captured_utc.isoformat(),
            "created_at": captured_utc.isoformat(),
            "cutoff": cutoff.isoformat(),
            "exclusions": exclusions,
            "organization_id": str(current_organization.pk),
            "predecessor_id": "0" * 36,
            "request_digest": "0" * 64,
            "reviewed_by_id": str(actor.pk),
            "rows": rows,
            "schema_version": EVIDENCE_SNAPSHOT_SOURCE_SCHEMA_VERSION,
            "snapshot_id": "0" * 36,
            "source_digest": source_digest,
            "source_id": normalized_source_id,
        }
    )
    if manifest_size > MAX_SNAPSHOT_MANIFEST_BYTES:
        raise ValidationError(
            f"evidence snapshot full manifest exceeds {MAX_SNAPSHOT_MANIFEST_BYTES} bytes"
        )
    request_digest = _digest(
        {
            "actor_id": str(actor.pk),
            "captured_at": captured_utc.isoformat(),
            "cutoff": cutoff.isoformat(),
            "exclusions": exclusions,
            "organization_id": str(current_organization.pk),
            "rows": rows,
            "source_digest": source_digest,
            "source_id": normalized_source_id,
        }
    )
    existing = (
        EvidenceSnapshotManifest.objects.select_for_update()
        .filter(organization=current_organization, source_id=normalized_source_id)
        .first()
    )
    if existing is not None:
        if existing.request_digest != request_digest:
            raise IdempotencyConflict("snapshot source_id was already used for different content")
        return EvidenceSnapshotOutcome(existing, True)
    record, _ = claim_idempotency(
        scope=f"evidence-snapshot:{current_organization.pk}",
        key=normalized_key,
        request_digest=request_digest,
    )
    replay = _snapshot_replay(record)
    if replay is not None:
        return replay
    predecessor = (
        EvidenceSnapshotManifest.objects.select_for_update()
        .filter(organization=current_organization)
        .order_by("-created_at", "-snapshot_id")
        .first()
    )
    snapshot = EvidenceSnapshotManifest.objects.create(
        organization=current_organization,
        source_id=normalized_source_id,
        cutoff=cutoff,
        captured_at=captured_utc,
        rows=rows,
        exclusions=exclusions,
        source_digest=source_digest,
        request_digest=request_digest,
        reviewed_by=actor,
        predecessor=predecessor,
    )
    record.status = IdempotencyRecord.Status.COMPLETED
    record.response = {"snapshot_id": str(snapshot.pk)}
    record.save(update_fields=["status", "response", "updated_at"])
    record_audit_event(
        actor_id=actor.pk,
        action="export.evidence_snapshot_generated",
        target_type="evidence_snapshot_manifest",
        target_id=str(snapshot.pk),
        payload_digest=request_digest,
        metadata={
            "excluded_row_count": len(exclusions),
            "organization_id": str(current_organization.pk),
            "row_count": len(rows),
            "source_digest": source_digest,
        },
    )
    return EvidenceSnapshotOutcome(snapshot, False)
