"""Machine-only narrow show inbox. Browser sessions confer no authority."""

import hashlib
import json

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from mnemex.partners.models import (
    ShowClientCredential,
    ShowResultConflict,
    ShowResultInbox,
    ShowResultStream,
)
from mnemex.partners.show_results import ShowResultError, receive_show_result


@csrf_exempt
@require_POST
def ingest_result(request):
    # This exemption is exclusively for the scoped bearer-authenticated machine
    # endpoint. All ordinary MNEMEX browser mutations retain Django CSRF.
    if not request.is_secure() and request.META.get("REMOTE_ADDR") not in {"127.0.0.1", "::1"}:
        return JsonResponse({"error": "tls_required"}, status=403)
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer ") or len(header) > 512:
        return JsonResponse({"error": "credential_required"}, status=401)
    credential = (
        ShowClientCredential.objects.select_related("client__organization")
        .filter(
            token_sha256=hashlib.sha256(header[7:].encode()).hexdigest(),
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .first()
    )
    if not credential:
        return JsonResponse({"error": "credential_invalid"}, status=401)
    try:
        if len(request.body) > 1024 * 1024:
            raise ShowResultError("request_capacity")
        receipt = receive_show_result(
            credential.client, credential.source_show_id, json.loads(request.body)
        )
        return JsonResponse(receipt, status=409 if receipt["state"] == "conflicting" else 200)
    except (ShowResultError, ValueError, TypeError, KeyError):
        return JsonResponse({"error": "show_result_refused"}, status=400)


@csrf_exempt
@require_POST
def result_status(request):
    if not request.is_secure() and request.META.get("REMOTE_ADDR") not in {"127.0.0.1", "::1"}:
        return JsonResponse({"error": "tls_required"}, status=403)
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer ") or len(header) > 512:
        return JsonResponse({"error": "credential_required"}, status=401)
    credential = (
        ShowClientCredential.objects.select_related("client__organization")
        .filter(
            token_sha256=hashlib.sha256(header[7:].encode()).hexdigest(),
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        .first()
    )
    if not credential or not credential.client.is_active:
        return JsonResponse({"error": "credential_invalid"}, status=401)
    streams = ShowResultStream.objects.filter(
        client=credential.client, source_show_id=credential.source_show_id
    )
    return JsonResponse(
        {
            "schema_version": "mnemex.show-result-status.v1",
            "stream_count": streams.count(),
            "source_revision_count": ShowResultInbox.objects.filter(stream__in=streams).count(),
            "conflict_count": ShowResultConflict.objects.filter(
                client=credential.client, source_show_id=credential.source_show_id
            ).count(),
            "streams": list(
                streams.order_by("source_result_id").values(
                    "source_result_id", "current_revision", "identity_state"
                )
            ),
        }
    )
