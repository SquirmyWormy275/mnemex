"""Atomic source-result reconciliation, independently of race-day operations.

The first receiver accepts synthetic individual SB/UH attempts. It preserves
unlinked identities and contiguous source revisions; archive export eligibility
and person reconciliation remain separate reviewed services.
"""

import hashlib
import json
import re
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction

from mnemex.foundation.services import IdempotencyConflict, claim_idempotency, record_audit_event
from mnemex.partners.models import (
    PartnerClient,
    ShowResultConflict,
    ShowResultInbox,
    ShowResultStream,
    ShowSource,
)


class ShowResultError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def result_binding(envelope):
    return digest({key: value for key, value in envelope.items() if key != "message_id"})


def closed(value, required, optional=()):
    if (
        not isinstance(value, dict)
        or set(value) - set(required) - set(optional)
        or set(required) - set(value)
    ):
        raise ShowResultError("invalid_show_result_fields")


def reference(value, limit=224):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= limit
        or not re.fullmatch(r"[A-Za-z0-9_.:/-]+", value)
    ):
        raise ShowResultError("invalid_source_reference")


def seconds(value, *, upper=86400, precision=6):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ShowResultError("invalid_seconds")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ShowResultError("invalid_seconds") from exc
    if not result.is_finite() or not 0 < result <= upper or result.as_tuple().exponent < -precision:
        raise ShowResultError("invalid_seconds")
    return result


def validate(envelope, source_show_id):
    closed(envelope, {"schema_version", "message_id", "source", "source_digest", "participant"})
    if envelope["schema_version"] != "mnemex.show-result.v1":
        raise ShowResultError("unsupported_show_result_contract")
    reference(envelope["message_id"])
    source = envelope["source"]
    closed(
        source,
        {
            "schema_version",
            "source_show_id",
            "source_event_id",
            "source_result_id",
            "source_revision",
            "heat_id",
            "field_digest",
            "issue_id",
            "discipline",
            "event_date",
            "wood",
            "outcome",
            "result_digest",
            "synthetic",
            "supersedes_source_digest",
            "correction_reason",
        },
    )
    if source["schema_version"] != "strathmark.source-result.v1" or source["synthetic"] is not True:
        raise ShowResultError("synthetic_source_contract_required")
    if source["source_show_id"] != source_show_id:
        raise ShowResultError("source_show_scope_mismatch")
    for key in ("source_show_id", "source_event_id", "heat_id"):
        reference(source[key])
    reference(source["source_result_id"], 512)
    if (
        type(source["source_revision"]) is not int
        or not 1 <= source["source_revision"] <= 2**31 - 1
    ):
        raise ShowResultError("invalid_source_revision")
    if envelope["source_digest"] != digest(source):
        raise ShowResultError("source_digest_mismatch")
    for key in ("field_digest", "issue_id", "result_digest"):
        if not isinstance(source[key], str) or not re.fullmatch(r"[0-9a-f]{64}", source[key]):
            raise ShowResultError("invalid_source_digest")
    if source["source_revision"] == 1:
        if (
            source["supersedes_source_digest"] is not None
            or source["correction_reason"] is not None
        ):
            raise ShowResultError("initial_revision_has_no_predecessor")
    elif (
        not isinstance(source["supersedes_source_digest"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", source["supersedes_source_digest"])
        or not isinstance(source["correction_reason"], str)
        or not 1 <= len(source["correction_reason"].strip()) <= 1000
    ):
        raise ShowResultError("correction_predecessor_and_reason_required")
    if source["discipline"] not in {"UH", "SB"}:
        raise ShowResultError("unsupported_show_discipline")
    try:
        date.fromisoformat(source["event_date"])
    except (TypeError, ValueError) as exc:
        raise ShowResultError("event_date_required") from exc
    closed(source["wood"], {"species", "diameter_mm", "quality"})
    reference(source["wood"]["species"])
    diameter = seconds(source["wood"]["diameter_mm"])
    quality = source["wood"]["quality"]
    if not 225 <= diameter <= 500 or (
        quality is not None and (type(quality) is not int or not 0 <= quality <= 10)
    ):
        raise ShowResultError("unsupported_wood")
    outcome = source["outcome"]
    closed(
        outcome,
        {
            "entry_id",
            "status",
            "raw_duration_seconds",
            "start_mark_seconds",
            "common_count_seconds",
            "official_position",
        },
        {"timer1_seconds", "timer2_seconds"},
    )
    reference(outcome["entry_id"])
    if outcome["status"] not in {"finished", "dnf", "dq", "dns", "scratched", "void"}:
        raise ShowResultError("invalid_outcome_status")
    if (
        type(outcome["start_mark_seconds"]) is not int
        or not 3 <= outcome["start_mark_seconds"] <= 183
    ):
        raise ShowResultError("invalid_start_mark")
    try:
        if outcome["status"] == "finished":
            raw = seconds(outcome["raw_duration_seconds"], precision=7)
            completion = seconds(outcome["common_count_seconds"], upper=86583, precision=7)
            if (
                type(outcome["official_position"]) is not int
                or not 1 <= outcome["official_position"] <= 512
            ):
                raise ShowResultError("invalid_official_position")
            timers = [
                seconds(outcome[key])
                for key in ("timer1_seconds", "timer2_seconds")
                if outcome.get(key) is not None
            ]
            if not timers or raw != sum(timers) / len(timers):
                raise ShowResultError("raw_timer_mean_mismatch")
            if (
                not raw.is_finite()
                or not 0 < raw <= 86400
                or completion != raw + outcome["start_mark_seconds"]
            ):
                raise ShowResultError("raw_duration_common_count_mismatch")
        elif (
            outcome["raw_duration_seconds"] is not None
            or outcome["common_count_seconds"] is not None
            or outcome["official_position"] is not None
            or any(outcome.get(key) is not None for key in ("timer1_seconds", "timer2_seconds"))
        ):
            raise ShowResultError("nonfinish_must_not_invent_time")
    except (TypeError, InvalidOperation) as exc:
        raise ShowResultError("invalid_raw_duration") from exc
    participant = envelope["participant"]
    closed(participant, {"show_person_ref", "unresolved_ref", "authorization_basis_ref"})
    if participant["unresolved_ref"] is not None:
        reference(participant["unresolved_ref"])
    if participant["show_person_ref"] is not None:
        reference(participant["show_person_ref"])
    if participant["authorization_basis_ref"] is not None:
        reference(participant["authorization_basis_ref"])
    if not participant["show_person_ref"] and not participant["unresolved_ref"]:
        raise ShowResultError("participant_reference_required")


def conflict(client, envelope, reason):
    payload_digest = result_binding(envelope)
    previous = ShowResultConflict.objects.filter(
        client=client, payload_digest=payload_digest
    ).first()
    if previous:
        return previous.receipt
    source = envelope["source"]
    receipt = {
        "schema_version": "mnemex.show-result-receipt.v1",
        "receipt_id": str(uuid.uuid4()),
        "payload_digest": payload_digest,
        "state": "conflicting",
        "reason": reason,
        "source_result_id": source["source_result_id"],
        "source_revision": source["source_revision"],
        "production_active": False,
        "career_state": "unlinked",
    }
    ShowResultConflict.objects.create(
        client=client,
        source_result_id=source["source_result_id"],
        source_revision=source["source_revision"],
        payload_digest=payload_digest,
        reason=reason,
        receipt=receipt,
    )
    record_audit_event(
        action="show_result.conflict",
        target_type="partner_client",
        target_id=str(client.pk),
        payload_digest=payload_digest,
        metadata={"reason": reason},
    )
    return receipt


@transaction.atomic
def receive_show_result(client, source_show_id, envelope):
    if not getattr(settings, "MNEMEX_SHOW_RESULTS_ENABLED", False):
        raise ShowResultError("show_result_receiver_disabled")
    validate(envelope, source_show_id)
    client = (
        PartnerClient.objects.select_for_update().select_related("organization").get(pk=client.pk)
    )
    if not client.is_active or client.environment != PartnerClient.Environment.SANDBOX:
        raise ShowResultError("active_sandbox_client_required: production qualification pending")
    if not ShowSource.objects.filter(source_show_id=source_show_id, client=client).exists():
        raise ShowResultError("source_show_not_registered_to_client")
    source = envelope["source"]
    payload_digest = result_binding(envelope)
    scope = "show-results:" + str(client.pk)
    try:
        idem, created = claim_idempotency(
            scope=scope, key=envelope["message_id"], request_digest=digest(envelope)
        )
    except IdempotencyConflict:
        return conflict(client, envelope, "request_identity_conflict")
    if not created and idem.response:
        return idem.response
    stream, _ = ShowResultStream.objects.get_or_create(
        client=client, source_show_id=source_show_id, source_result_id=source["source_result_id"]
    )
    previous = ShowResultInbox.objects.filter(
        stream=stream, source_revision=source["source_revision"]
    ).first()
    if previous:
        if previous.payload_digest != payload_digest:
            receipt = conflict(client, envelope, "source_revision_conflict")
        else:
            receipt = previous.receipt
        idem.status, idem.response = "completed", receipt
        idem.save(update_fields=("status", "response", "updated_at"))
        return receipt
    identity_state = "unlinked"  # A reference is not consent or identity proof.
    state = (
        identity_state
        if source["source_revision"] == stream.current_revision + 1
        else "pending_predecessor"
    )
    receipt = {
        "schema_version": "mnemex.show-result-receipt.v1",
        "receipt_id": str(uuid.uuid4()),
        "source_result_id": source["source_result_id"],
        "source_revision": source["source_revision"],
        "payload_digest": payload_digest,
        "state": state,
        "career_state": identity_state,
        "production_active": False,
    }
    row = ShowResultInbox.objects.create(
        stream=stream,
        source_revision=source["source_revision"],
        message_id=envelope["message_id"],
        payload_digest=payload_digest,
        payload=envelope,
        receipt=receipt,
    )
    while True:
        next_row = ShowResultInbox.objects.filter(
            stream=stream, source_revision=stream.current_revision + 1
        ).first()
        if not next_row:
            break
        if stream.current_revision:
            prior = ShowResultInbox.objects.get(
                stream=stream, source_revision=stream.current_revision
            )
            if (
                next_row.payload["source"]["supersedes_source_digest"]
                != prior.payload["source_digest"]
            ):
                conflict(client, next_row.payload, "source_predecessor_conflict")
                break
            if any(
                next_row.payload["source"][key] != prior.payload["source"][key]
                for key in ("source_event_id", "heat_id", "field_digest", "issue_id")
            ):
                conflict(client, next_row.payload, "issued_source_binding_conflict")
                break
        stream.current_revision += 1
    stream.identity_state = identity_state
    stream.save(update_fields=("current_revision", "identity_state"))
    idem.status, idem.response = "completed", receipt
    idem.save(update_fields=("status", "response", "updated_at"))
    record_audit_event(
        action="show_result.received",
        target_type="show_result",
        target_id=str(row.pk),
        payload_digest=payload_digest,
        metadata={"source_revision": source["source_revision"], "state": state},
    )
    return receipt
