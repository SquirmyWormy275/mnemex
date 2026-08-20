from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import timedelta

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.utils import timezone

from mnemex.partners.models import PartnerOrganization
from mnemex.results.artifact_lifecycle import (
    abandon_artifact_write,
    begin_artifact_write,
    reconcile_artifact_objects,
)
from mnemex.results.artifacts import (
    ArtifactCollisionError,
    ArtifactReadTooLargeError,
    RequestsSupabaseStorageTransport,
    SupabasePrivateArtifactStore,
    private_artifact_store_from_settings,
)
from mnemex.results.models import ArtifactObjectWrite


@dataclass
class FakePrivateObjectTransport:
    objects: dict[str, bytes] = field(default_factory=dict)
    read_limits: list[int] = field(default_factory=list)
    creates: list[str] = field(default_factory=list)
    deletes: list[str] = field(default_factory=list)

    def create(self, *, reference: str, content: bytes) -> bool:
        self.creates.append(reference)
        if reference in self.objects:
            return False
        self.objects[reference] = content
        return True

    def read(self, *, reference: str, max_bytes: int) -> bytes:
        self.read_limits.append(max_bytes)
        try:
            content = self.objects[reference]
        except KeyError as error:
            raise FileNotFoundError(reference) from error
        if len(content) > max_bytes:
            raise ArtifactReadTooLargeError("private object exceeds its bounded read limit")
        return content

    def remove(self, *, reference: str) -> bool:
        self.deletes.append(reference)
        return self.objects.pop(reference, None) is not None


def _store(
    transport: FakePrivateObjectTransport | None = None,
    *,
    max_read_bytes: int = 1024,
) -> tuple[SupabasePrivateArtifactStore, FakePrivateObjectTransport]:
    current = transport or FakePrivateObjectTransport()
    return (
        SupabasePrivateArtifactStore(
            bucket="mnemex-private-artifacts",
            bucket_is_public=False,
            transport=current,
            max_read_bytes=max_read_bytes,
        ),
        current,
    )


def test_supabase_store_uses_opaque_digest_keys_and_verifies_upload() -> None:
    store, transport = _store()
    content = b"synthetic hosted workbook"

    reference = store.put(content=content, filename="competitor names.xlsx")

    digest = hashlib.sha256(content).hexdigest()
    assert reference == f"sha256/{digest[:2]}/{digest[2:4]}/{digest}.xlsx"
    assert transport.objects[reference] == content
    assert transport.read_limits == [1024]
    assert "competitor" not in reference
    assert not hasattr(store, "public_url")


def test_supabase_store_treats_identical_concurrent_create_as_idempotent() -> None:
    store, transport = _store()
    content = b"same bytes from two uploads"

    first = store.put(content=content, filename="first.xlsx")
    second = store.put(content=content, filename="renamed.xlsx")

    assert first == second
    assert transport.creates == [first, first]
    assert transport.objects == {first: content}


def test_supabase_store_rejects_wrong_bytes_at_a_digest_address() -> None:
    store, transport = _store()
    expected = b"expected bytes"
    reference = store.reference_for(content=expected, filename="expected.xlsx")
    transport.objects[reference] = b"different bytes"

    with pytest.raises(ArtifactCollisionError, match="different bytes"):
        store.put(content=expected, filename="expected.xlsx")

    assert transport.objects[reference] == b"different bytes"
    assert transport.deletes == []


def test_supabase_store_rejects_invalid_and_oversized_reads() -> None:
    store, transport = _store(max_read_bytes=8)
    content = b"larger than eight bytes"
    reference = store.reference_for(content=content, filename="large.csv")
    transport.objects[reference] = content

    with pytest.raises(ValueError, match="digest-addressed"):
        store.read(reference="../outside.xlsx")
    with pytest.raises(ArtifactReadTooLargeError, match="bounded read"):
        store.read(reference=reference)

    assert transport.read_limits == [8]


def test_supabase_store_rejects_tampered_download_digest() -> None:
    store, transport = _store()
    expected = b"expected bytes"
    reference = store.reference_for(content=expected, filename="expected.csv")
    transport.objects[reference] = b"tampered bytes"

    with pytest.raises(ArtifactCollisionError, match="digest address"):
        store.read(reference=reference)


def test_supabase_remove_preserves_changed_object() -> None:
    store, transport = _store()
    original = b"original bytes"
    reference = store.put(content=original, filename="original.xlsx")
    transport.objects[reference] = b"changed bytes"

    assert not store.remove_if_exact(reference=reference, content=original)
    assert transport.objects[reference] == b"changed bytes"
    assert transport.deletes == []


@pytest.mark.django_db
def test_supabase_reconciliation_records_tamper_without_deleting_bytes() -> None:
    store, transport = _store()
    organization = PartnerOrganization.objects.create(name="Synthetic Hosted Storage Show")
    content = b"expected hosted object"
    now = timezone.now()
    attempt = begin_artifact_write(
        organization=organization,
        content=content,
        filename="hosted.xlsx",
        now=now,
    )
    reference = attempt.artifact_object.object_reference
    transport.objects[reference] = b"tampered hosted object"
    abandon_artifact_write(
        attempt=attempt,
        error_code="synthetic_failure",
        now=now,
        cleanup_grace=timedelta(0),
    )

    outcome = reconcile_artifact_objects(store=store, now=now, limit=10)

    attempt.refresh_from_db()
    assert outcome.blocked == 1
    assert attempt.status == ArtifactObjectWrite.Status.BLOCKED
    assert attempt.error_code == "object_digest_mismatch"
    assert transport.objects[reference] == b"tampered hosted object"
    assert transport.deletes == []


@override_settings(
    MNEMEX_PRIVATE_ARTIFACT_BACKEND="supabase",
    MNEMEX_PRIVATE_ARTIFACT_BUCKET="mnemex-private-artifacts",
    MNEMEX_PRIVATE_ARTIFACT_BUCKET_IS_PUBLIC=False,
    MNEMEX_PRIVATE_ARTIFACT_MAX_BYTES=4096,
)
def test_factory_selects_supabase_without_hosted_credentials_when_transport_is_injected() -> None:
    transport = FakePrivateObjectTransport()

    store = private_artifact_store_from_settings(transport=transport)

    assert isinstance(store, SupabasePrivateArtifactStore)
    assert store.max_read_bytes == 4096


@override_settings(
    MNEMEX_PRIVATE_ARTIFACT_BACKEND="supabase",
    MNEMEX_PRIVATE_ARTIFACT_BUCKET="mnemex-private-artifacts",
    MNEMEX_PRIVATE_ARTIFACT_BUCKET_IS_PUBLIC=False,
    MNEMEX_SUPABASE_URL="https://synthetic-project.supabase.co",
    MNEMEX_SUPABASE_SERVICE_ROLE_KEY="synthetic-server-only-service-key",
    MNEMEX_PRIVATE_ARTIFACT_MAX_BYTES=4096,
)
def test_factory_builds_server_transport_from_hosted_setting_contract() -> None:
    store = private_artifact_store_from_settings()

    assert isinstance(store, SupabasePrivateArtifactStore)
    assert store.max_read_bytes == 4096


@pytest.mark.parametrize("public_value", [True, None, "false"])
def test_factory_rejects_bucket_configuration_not_explicitly_private(public_value: object) -> None:
    with override_settings(
        MNEMEX_PRIVATE_ARTIFACT_BACKEND="supabase",
        MNEMEX_PRIVATE_ARTIFACT_BUCKET="mnemex-private-artifacts",
        MNEMEX_PRIVATE_ARTIFACT_BUCKET_IS_PUBLIC=public_value,
        MNEMEX_PRIVATE_ARTIFACT_MAX_BYTES=4096,
    ):
        with pytest.raises(ImproperlyConfigured, match="explicitly private"):
            private_artifact_store_from_settings(transport=FakePrivateObjectTransport())


def test_factory_rejects_unknown_backend() -> None:
    with override_settings(MNEMEX_PRIVATE_ARTIFACT_BACKEND="public-cdn"):
        with pytest.raises(ImproperlyConfigured, match="backend"):
            private_artifact_store_from_settings()


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        *,
        chunks: tuple[bytes, ...] = (),
        headers: dict[str, str] | None = None,
        payload: object = None,
    ) -> None:
        self.status_code = status_code
        self._chunks = chunks
        self.headers = headers or {}
        self._payload = payload
        self.closed = False
        self.iterated = False

    def iter_content(self, *, chunk_size: int) -> tuple[bytes, ...]:
        assert chunk_size == 64 * 1024
        self.iterated = True
        return self._chunks

    def close(self) -> None:
        self.closed = True

    def json(self) -> object:
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(("POST", url, kwargs))
        return self.response

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(("GET", url, kwargs))
        return self.response

    def delete(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(("DELETE", url, kwargs))
        return self.response


def _requests_transport(
    session: FakeSession,
) -> RequestsSupabaseStorageTransport:
    return RequestsSupabaseStorageTransport(
        supabase_url="https://synthetic-project.supabase.co",
        service_key="synthetic-server-only-service-key",
        bucket="mnemex-private-artifacts",
        session=session,  # type: ignore[arg-type]
    )


def _canonical_reference() -> str:
    digest = "a" * 64
    return f"sha256/aa/aa/{digest}.xlsx"


def test_http_transport_create_is_non_overwriting_and_conflict_is_idempotent() -> None:
    session = FakeSession(FakeResponse(409))
    transport = _requests_transport(session)

    assert not transport.create(reference=_canonical_reference(), content=b"bytes")

    method, url, kwargs = session.calls[0]
    assert method == "POST"
    assert url.startswith("https://synthetic-project.supabase.co/storage/v1/object/")
    assert kwargs["headers"]["x-upsert"] == "false"  # type: ignore[index]
    assert kwargs["files"] == {"file": (("a" * 64) + ".xlsx", b"bytes", "application/octet-stream")}


def test_http_transport_never_follows_redirects_with_server_credentials() -> None:
    reference = _canonical_reference()
    operations = (
        ("POST", lambda transport: transport.create(reference=reference, content=b"bytes")),
        ("GET", lambda transport: transport.read(reference=reference, max_bytes=8)),
        ("DELETE", lambda transport: transport.remove(reference=reference)),
    )

    for method, operation in operations:
        session = FakeSession(FakeResponse(302))
        transport = _requests_transport(session)
        with pytest.raises(OSError, match="status 302"):
            operation(transport)
        assert session.calls[0][0] == method
        assert session.calls[0][2]["allow_redirects"] is False


def test_http_transport_rejects_declared_oversize_before_buffering() -> None:
    response = FakeResponse(200, chunks=(b"too large",), headers={"Content-Length": "9"})
    transport = _requests_transport(FakeSession(response))

    with pytest.raises(ArtifactReadTooLargeError, match="bounded read"):
        transport.read(reference=_canonical_reference(), max_bytes=8)

    assert response.closed
    assert not response.iterated


def test_http_transport_stops_stream_when_actual_bytes_exceed_limit() -> None:
    response = FakeResponse(200, chunks=(b"1234", b"56789"))
    transport = _requests_transport(FakeSession(response))

    with pytest.raises(ArtifactReadTooLargeError, match="bounded read"):
        transport.read(reference=_canonical_reference(), max_bytes=8)

    assert response.closed
    assert response.iterated


def test_http_transport_rejects_noncanonical_key_before_request() -> None:
    session = FakeSession(FakeResponse(200))
    transport = _requests_transport(session)

    with pytest.raises(ValueError, match="digest-addressed"):
        transport.read(reference="../private.xlsx", max_bytes=8)

    assert session.calls == []


def test_http_transport_rejects_insecure_or_credential_bearing_origins() -> None:
    for url in (
        "http://synthetic-project.supabase.co",
        "https://user:secret@synthetic-project.supabase.co",
        "https://synthetic-project.supabase.co/path",
    ):
        with pytest.raises(ImproperlyConfigured, match="HTTPS origin"):
            RequestsSupabaseStorageTransport(
                supabase_url=url,
                service_key="synthetic-server-only-service-key",
                bucket="mnemex-private-artifacts",
            )
