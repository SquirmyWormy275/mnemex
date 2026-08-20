from __future__ import annotations

import uuid
from typing import Any, NoReturn

from django.core.exceptions import PermissionDenied
from django.db import models


class AppendOnlyQuerySet(models.QuerySet["AuditEvent"]):
    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("Audit events are append-only")

    def delete(self) -> NoReturn:
        raise PermissionDenied("Audit events are append-only")


class AuditEvent(models.Model):
    """PII-minimized immutable record of a security or domain action."""

    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=120)
    target_type = models.CharField(max_length=80)
    target_id = models.CharField(max_length=160)
    correlation_id = models.UUIDField(default=uuid.uuid4, editable=False)
    payload_digest = models.CharField(max_length=64)
    metadata = models.JSONField(default=dict)
    occurred_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        default_permissions = ("add", "view")
        ordering = ("occurred_at", "event_id")
        indexes = [
            models.Index(fields=("target_type", "target_id"), name="audit_target_idx"),
            models.Index(fields=("correlation_id",), name="audit_correlation_idx"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise PermissionDenied("Audit events are append-only")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("Audit events are append-only")


class IdempotencyRecord(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    record_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scope = models.CharField(max_length=120)
    key = models.CharField(max_length=200)
    request_digest = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    response = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("scope", "key"), name="unique_idempotency_scope_key")
        ]
        indexes = [models.Index(fields=("scope", "status"), name="idempotency_status_idx")]
