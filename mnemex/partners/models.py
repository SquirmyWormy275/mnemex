from __future__ import annotations

import uuid

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
