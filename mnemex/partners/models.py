from __future__ import annotations

import uuid

from django.core.exceptions import PermissionDenied
from django.db import models


class PartnerOrganization(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    organization_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class PartnerClient(models.Model):
    class Environment(models.TextChoices):
        SANDBOX = "sandbox", "Sandbox"
        STAGING = "staging", "Staging"
        PRODUCTION = "production", "Production"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        REVOKED = "revoked", "Revoked"

    client_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization, on_delete=models.PROTECT, related_name="clients"
    )
    name = models.CharField(max_length=160)
    environment = models.CharField(max_length=20, choices=Environment.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    allowed_purposes = models.JSONField(default=list)
    allowed_field_groups = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "name", "environment"),
                name="unique_partner_client_environment",
            )
        ]
        indexes = [
            models.Index(
                fields=("organization", "environment", "status"),
                name="partner_client_scope_idx",
            )
        ]

    @property
    def is_active(self) -> bool:
        return (
            self.status == self.Status.ACTIVE
            and self.revoked_at is None
            and self.organization.status == PartnerOrganization.Status.ACTIVE
        )


class ShowClientCredential(models.Model):
    """Narrow machine credential; no database or browser authority."""

    credential_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(PartnerClient, on_delete=models.PROTECT)
    source_show_id = models.CharField(max_length=224)
    token_sha256 = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)


class ShowSource(models.Model):
    source_show_id = models.CharField(max_length=224, primary_key=True)
    client = models.ForeignKey(PartnerClient, on_delete=models.PROTECT)


class ShowResultStream(models.Model):
    client = models.ForeignKey(PartnerClient, on_delete=models.PROTECT)
    source_show_id = models.CharField(max_length=224)
    source_result_id = models.CharField(max_length=512)
    current_revision = models.PositiveIntegerField(default=0)
    identity_state = models.CharField(max_length=32, default="unlinked")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("client", "source_show_id", "source_result_id"),
                name="unique_show_result_stream",
            )
        ]


class ImmutableShowQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionDenied("show source revisions are immutable")

    def delete(self):
        raise PermissionDenied("show source revisions are immutable")


class ShowResultInbox(models.Model):
    receipt_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stream = models.ForeignKey(ShowResultStream, on_delete=models.PROTECT, related_name="revisions")
    source_revision = models.PositiveIntegerField()
    message_id = models.CharField(max_length=224)
    payload_digest = models.CharField(max_length=64)
    payload = models.JSONField()
    receipt = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableShowQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("stream", "source_revision"), name="unique_show_source_revision"
            ),
            models.CheckConstraint(
                condition=models.Q(source_revision__gte=1), name="show_source_revision_positive"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionDenied("show source revisions are immutable")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("show source revisions are immutable")


class ShowResultConflict(models.Model):
    # Existing unattributed conflict receipts remain private, never guessed.
    source_show_id = models.CharField(max_length=224, null=True)
    conflict_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(PartnerClient, on_delete=models.PROTECT)
    source_result_id = models.CharField(max_length=512)
    source_revision = models.PositiveIntegerField()
    payload_digest = models.CharField(max_length=64)
    reason = models.CharField(max_length=80)
    receipt = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("client", "payload_digest"), name="unique_show_conflict_payload"
            )
        ]
