from __future__ import annotations

import hashlib
import hmac
import os
import re
import tempfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import quote, urlparse

import requests  # type: ignore[import-untyped]
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class ArtifactCollisionError(RuntimeError):
    """A digest address already exists with different bytes."""


class ArtifactReadTooLargeError(OSError):
    """A private object exceeded the configured bounded-read limit."""


class PrivateArtifactStore(Protocol):
    """Minimal private-object behavior used by upload and reconciliation flows."""

    def put(self, *, content: bytes, filename: str) -> str: ...

    def read(self, *, reference: str) -> bytes: ...

    def remove_if_exact(self, *, reference: str, content: bytes) -> bool: ...


class SupabaseStorageTransport(Protocol):
    """Server-side transport surface, kept injectable for credential-free tests."""

    def create(self, *, reference: str, content: bytes) -> bool: ...

    def read(self, *, reference: str, max_bytes: int) -> bytes: ...

    def remove(self, *, reference: str) -> bool: ...


_DIGEST_REFERENCE = re.compile(
    r"^sha256/(?P<first>[0-9a-f]{2})/(?P<second>[0-9a-f]{2})/"
    r"(?P<digest>[0-9a-f]{64})(?P<suffix>\.csv|\.xlsx|\.bin)$"
)
_BUCKET_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$")
_DEFAULT_MAX_ARTIFACT_BYTES = 25 * 1024 * 1024


def artifact_reference_for(*, content: bytes, filename: str) -> str:
    """Return a filename-free, digest-addressed private object reference."""

    digest = hashlib.sha256(content).hexdigest()
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".xlsx"}:
        suffix = ".bin"
    return PurePosixPath("sha256", digest[:2], digest[2:4], f"{digest}{suffix}").as_posix()


def _digest_from_reference(reference: str) -> str:
    match = _DIGEST_REFERENCE.fullmatch(reference)
    if match is None:
        raise ValueError("artifact reference must be a canonical digest-addressed key")
    digest = match.group("digest")
    if match.group("first") != digest[:2] or match.group("second") != digest[2:4]:
        raise ValueError("artifact reference must be a canonical digest-addressed key")
    return digest


class LocalPrivateArtifactStore:
    """Small local-only private artifact adapter for development and tests.

    This adapter is intentionally not a Supabase Storage implementation. Database
    rows receive only digest-derived relative references.
    """

    def __init__(self, root: str | Path | None) -> None:
        if root is None or not str(root).strip():
            raise ImproperlyConfigured("Private artifact storage is not configured.")
        self.root = Path(root).expanduser().resolve()

    @staticmethod
    def reference_for(*, content: bytes, filename: str) -> str:
        return artifact_reference_for(content=content, filename=filename)

    def _target_for(self, reference: str) -> Path:
        relative = PurePosixPath(reference)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("artifact reference must stay below the private artifact root")
        target = self.root.joinpath(*relative.parts).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("artifact reference must stay below the private artifact root")
        return target

    @staticmethod
    def _assert_exact(target: Path, content: bytes) -> None:
        try:
            existing = target.read_bytes()
        except FileNotFoundError:
            raise ArtifactCollisionError("artifact disappeared during exclusive installation")
        if not hmac.compare_digest(existing, content):
            raise ArtifactCollisionError("artifact digest address contains different bytes")

    def put(self, *, content: bytes, filename: str) -> str:
        reference = self.reference_for(content=content, filename=filename)
        target = self._target_for(reference)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            self._assert_exact(target, content)
            return reference

        descriptor, temporary_name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as artifact:
                artifact.write(content)
                artifact.flush()
                os.fsync(artifact.fileno())
            try:
                # A hard link within the same directory gives an atomic, exclusive
                # final name: it fails rather than replacing an existing object.
                os.link(temporary, target)
            except FileExistsError:
                self._assert_exact(target, content)
            return reference
        finally:
            temporary.unlink(missing_ok=True)

    def read(self, *, reference: str) -> bytes:
        """Read one private object through the same containment boundary as writes."""

        target = self._target_for(reference)
        return target.read_bytes()

    def remove_if_exact(self, *, reference: str, content: bytes) -> bool:
        """Remove one unreferenced object only when its bytes still match.

        Database provenance ownership is deliberately checked by the caller;
        this adapter only enforces path containment and exact-byte deletion.
        """

        target = self._target_for(reference)
        try:
            existing = target.read_bytes()
        except FileNotFoundError:
            return False
        if not hmac.compare_digest(existing, content):
            return False
        target.unlink()
        return True


class RequestsSupabaseStorageTransport:
    """Bounded private Storage API transport using server-only credentials.

    It deliberately exposes no signed/public URL behavior. Uploads are create-only;
    an existing digest address is verified by the store rather than overwritten.
    """

    def __init__(
        self,
        *,
        supabase_url: str,
        service_key: str,
        bucket: str,
        timeout_seconds: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        parsed = urlparse(supabase_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ImproperlyConfigured("Supabase Storage URL must be an HTTPS origin.")
        if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
            raise ImproperlyConfigured("Supabase Storage URL must be an HTTPS origin.")
        if not service_key.strip():
            raise ImproperlyConfigured("Supabase Storage service credential is required.")
        if not _BUCKET_NAME.fullmatch(bucket):
            raise ImproperlyConfigured("Supabase Storage bucket name is invalid.")
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ImproperlyConfigured("Supabase Storage timeout must be from 0 to 60 seconds.")
        self._origin = supabase_url.rstrip("/")
        self._bucket = bucket
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()
        self._headers = {
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
        }

    def _object_url(self, reference: str) -> str:
        _digest_from_reference(reference)
        bucket = quote(self._bucket, safe="")
        key = quote(reference, safe="/")
        return f"{self._origin}/storage/v1/object/{bucket}/{key}"

    @staticmethod
    def _chunks(response: requests.Response) -> Iterator[bytes]:
        yield from response.iter_content(chunk_size=64 * 1024)

    def create(self, *, reference: str, content: bytes) -> bool:
        try:
            response = self._session.post(
                self._object_url(reference),
                headers={
                    **self._headers,
                    "x-upsert": "false",
                },
                files={
                    "file": (
                        PurePosixPath(reference).name,
                        content,
                        "application/octet-stream",
                    )
                },
                timeout=self._timeout_seconds,
                allow_redirects=False,
            )
        except requests.RequestException as error:
            raise OSError("private object create request failed") from error
        if response.status_code == 409:
            return False
        if response.status_code not in {200, 201}:
            raise OSError(f"private object create failed with status {response.status_code}")
        return True

    def read(self, *, reference: str, max_bytes: int) -> bytes:
        try:
            response = self._session.get(
                self._object_url(reference),
                headers=self._headers,
                timeout=self._timeout_seconds,
                stream=True,
                allow_redirects=False,
            )
        except requests.RequestException as error:
            raise OSError("private object read request failed") from error
        if response.status_code == 404:
            response.close()
            raise FileNotFoundError(reference)
        if response.status_code != 200:
            response.close()
            raise OSError(f"private object read failed with status {response.status_code}")
        declared_length = response.headers.get("Content-Length")
        if declared_length is not None:
            try:
                parsed_length = int(declared_length)
            except ValueError as error:
                response.close()
                raise OSError("private object read returned an invalid length") from error
            if parsed_length < 0:
                response.close()
                raise OSError("private object read returned an invalid length")
            if parsed_length > max_bytes:
                response.close()
                raise ArtifactReadTooLargeError("private object exceeds its bounded read limit")
        content = bytearray()
        try:
            for chunk in self._chunks(response):
                if not chunk:
                    continue
                content.extend(chunk)
                if len(content) > max_bytes:
                    raise ArtifactReadTooLargeError("private object exceeds its bounded read limit")
        except requests.RequestException as error:
            raise OSError("private object read request failed") from error
        finally:
            response.close()
        return bytes(content)

    def remove(self, *, reference: str) -> bool:
        _digest_from_reference(reference)
        bucket = quote(self._bucket, safe="")
        try:
            response = self._session.delete(
                f"{self._origin}/storage/v1/object/{bucket}",
                headers={**self._headers, "Content-Type": "application/json"},
                json={"prefixes": [reference]},
                timeout=self._timeout_seconds,
                allow_redirects=False,
            )
        except requests.RequestException as error:
            raise OSError("private object remove request failed") from error
        if response.status_code == 404:
            return False
        if response.status_code not in {200, 204}:
            raise OSError(f"private object remove failed with status {response.status_code}")
        if response.status_code == 204:
            return True
        try:
            payload = response.json()
        except requests.JSONDecodeError as error:
            raise OSError("private object remove returned an invalid response") from error
        return isinstance(payload, list) and bool(payload)


class SupabasePrivateArtifactStore:
    """Digest-verifying adapter for one explicitly private Supabase bucket."""

    def __init__(
        self,
        *,
        bucket: str,
        bucket_is_public: bool,
        transport: SupabaseStorageTransport,
        max_read_bytes: int = _DEFAULT_MAX_ARTIFACT_BYTES,
    ) -> None:
        if bucket_is_public is not False:
            raise ImproperlyConfigured("Supabase artifact bucket must be explicitly private.")
        if not _BUCKET_NAME.fullmatch(bucket):
            raise ImproperlyConfigured("Supabase Storage bucket name is invalid.")
        if (
            isinstance(max_read_bytes, bool)
            or not isinstance(max_read_bytes, int)
            or not 1 <= max_read_bytes <= 100 * 1024 * 1024
        ):
            raise ImproperlyConfigured(
                "Private artifact maximum size must be from 1 byte to 100 MiB."
            )
        self.bucket = bucket
        self.max_read_bytes = max_read_bytes
        self._transport = transport

    @staticmethod
    def reference_for(*, content: bytes, filename: str) -> str:
        return artifact_reference_for(content=content, filename=filename)

    def put(self, *, content: bytes, filename: str) -> str:
        if len(content) > self.max_read_bytes:
            raise ArtifactReadTooLargeError("private object exceeds its bounded read limit")
        reference = self.reference_for(content=content, filename=filename)
        self._transport.create(reference=reference, content=content)
        try:
            installed = self.read(reference=reference)
        except ArtifactCollisionError:
            raise
        if not hmac.compare_digest(installed, content):
            raise ArtifactCollisionError("artifact digest address contains different bytes")
        return reference

    def read(self, *, reference: str) -> bytes:
        expected_digest = _digest_from_reference(reference)
        content = self._transport.read(
            reference=reference,
            max_bytes=self.max_read_bytes,
        )
        actual_digest = hashlib.sha256(content).hexdigest()
        if not hmac.compare_digest(actual_digest, expected_digest):
            raise ArtifactCollisionError("artifact digest address contains different bytes")
        return content

    def remove_if_exact(self, *, reference: str, content: bytes) -> bool:
        try:
            existing = self.read(reference=reference)
        except (FileNotFoundError, ArtifactCollisionError):
            return False
        if not hmac.compare_digest(existing, content):
            return False
        return self._transport.remove(reference=reference)


def private_artifact_store_from_settings(
    *,
    transport: SupabaseStorageTransport | None = None,
) -> PrivateArtifactStore:
    """Build the configured private store without ever returning a public client."""

    backend = str(getattr(settings, "MNEMEX_PRIVATE_ARTIFACT_BACKEND", "local"))
    if backend == "local":
        return LocalPrivateArtifactStore(getattr(settings, "MNEMEX_PRIVATE_ARTIFACT_ROOT", None))
    if backend != "supabase":
        raise ImproperlyConfigured("Private artifact storage backend is invalid.")

    bucket = str(getattr(settings, "MNEMEX_PRIVATE_ARTIFACT_BUCKET", ""))
    bucket_is_public = getattr(settings, "MNEMEX_PRIVATE_ARTIFACT_BUCKET_IS_PUBLIC", None)
    max_read_bytes = getattr(
        settings,
        "MNEMEX_PRIVATE_ARTIFACT_MAX_BYTES",
        _DEFAULT_MAX_ARTIFACT_BYTES,
    )
    if bucket_is_public is not False:
        raise ImproperlyConfigured("Supabase artifact bucket must be explicitly private.")
    if transport is None:
        transport = RequestsSupabaseStorageTransport(
            supabase_url=str(getattr(settings, "MNEMEX_SUPABASE_URL", "")),
            service_key=str(getattr(settings, "MNEMEX_SUPABASE_SERVICE_ROLE_KEY", "")),
            bucket=bucket,
        )
    return SupabasePrivateArtifactStore(
        bucket=bucket,
        bucket_is_public=bucket_is_public,
        transport=transport,
        max_read_bytes=max_read_bytes,
    )
