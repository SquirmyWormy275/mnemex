from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

from mnemex.legacy_migration.models import LegacyMigrationRun
from mnemex.results.artifacts import (
    ArtifactCollisionError,
    LocalPrivateArtifactStore,
    PrivateArtifactStore,
    private_artifact_store_from_settings,
)


class PrivateWorkbookUnavailable(OSError):
    """The verified private source could not be read from storage."""


def read_private_workbook(
    run: LegacyMigrationRun,
    *,
    artifact_root: str | Path | None = None,
) -> bytes:
    """Read one exact private source and verify its immutable manifest."""

    artifact = run.inventory.artifact
    store: PrivateArtifactStore
    if artifact_root is not None:
        store = LocalPrivateArtifactStore(artifact_root)
    elif getattr(settings, "MNEMEX_PRIVATE_ARTIFACT_BACKEND", "local") == "local":
        store = LocalPrivateArtifactStore(getattr(settings, "MNEMEX_PRIVATE_ARTIFACT_ROOT", None))
    else:
        store = private_artifact_store_from_settings()
    try:
        content = store.read(reference=artifact.object_reference)
    except ValueError as error:
        raise ValidationError("private workbook reference is invalid") from error
    except ArtifactCollisionError as error:
        raise ValidationError(
            "private workbook content no longer matches its immutable artifact manifest"
        ) from error
    except OSError as error:
        raise PrivateWorkbookUnavailable("private workbook content is unavailable") from error
    digest = hashlib.sha256(content).hexdigest()
    if not hmac.compare_digest(digest, artifact.digest) or len(content) != artifact.byte_size:
        raise ValidationError(
            "private workbook content no longer matches its immutable artifact manifest"
        )
    return content
