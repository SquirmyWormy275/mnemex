from __future__ import annotations

import uuid
from typing import Any, ClassVar, NoReturn

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.crypto import salted_hmac

from mnemex.accounts.managers import AccountManager


class Account(AbstractBaseUser, PermissionsMixin):
    """A login account, deliberately separate from a competitor Person record."""

    account_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    mfa_enrolled_at = models.DateTimeField(null=True, blank=True)
    security_version = models.PositiveIntegerField(default=1)

    objects = AccountManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        ordering = ("email",)
        constraints = [
            models.UniqueConstraint(Lower("email"), name="unique_account_email_ci"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.email

    def _get_session_auth_hash(self, secret: str | None = None) -> str:
        """Bind Django sessions to password and MNEMEX security revision."""

        return salted_hmac(
            "mnemex.accounts.Account.session_auth_hash",
            f"{self.password}:{self.security_version}",
            secret=secret,
            algorithm="sha256",
        ).hexdigest()


class PrivilegedRoleAssignment(models.Model):
    class Scope(models.TextChoices):
        PLATFORM = "platform", "Platform wide"
        ORGANIZATION = "organization", "Partner organization"

    class Role(models.TextChoices):
        RESULTS_MANAGER = "results_manager", "Results manager"
        EXPORT_REVIEWER = "export_reviewer", "Results export reviewer"
        IDENTITY_REVIEWER = "identity_reviewer", "Identity reviewer"
        PRIVACY_OFFICER = "privacy_officer", "Privacy officer"
        PARTNER_ADMINISTRATOR = "partner_administrator", "Partner administrator"
        SECURITY_ADMINISTRATOR = "security_administrator", "Security administrator"

    assignment_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="privileged_roles")
    role = models.CharField(max_length=40, choices=Role.choices)
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.PLATFORM)
    organization = models.ForeignKey(
        "partners.PartnerOrganization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="privileged_role_assignments",
    )
    assigned_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="assigned_privileged_roles",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(scope="platform", organization__isnull=True)
                    | Q(scope="organization", organization__isnull=False)
                ),
                name="valid_priv_role_scope",
            ),
            models.UniqueConstraint(
                fields=("account", "role"),
                condition=Q(revoked_at__isnull=True, scope="platform"),
                name="unique_active_platform_role",
            ),
            models.UniqueConstraint(
                fields=("account", "role", "organization"),
                condition=Q(revoked_at__isnull=True, scope="organization"),
                name="unique_active_org_role",
            ),
        ]
        indexes = [
            models.Index(fields=("role", "revoked_at"), name="role_active_idx"),
            models.Index(
                fields=("role", "scope", "organization", "revoked_at"),
                name="role_scope_active_idx",
            ),
        ]

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class SecurityNotification(models.Model):
    """A PII-minimized, durable intent for one security notification."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        RETRY_WAIT = "retry_wait", "Retry wait"
        DELIVERED = "delivered", "Delivered"
        FAILED_REVIEW = "failed_review", "Failed - review required"
        DELIVERY_UNCERTAIN = "delivery_uncertain", "Delivery uncertain"
        EXPIRED = "expired", "Recipient retention expired"

    class DeliveryPhase(models.TextChoices):
        PRE_HANDOFF = "pre_handoff", "Before SMTP handoff"
        HANDOFF = "handoff", "SMTP handoff began"

    notification_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="security_notifications",
    )
    template_identifier = models.CharField(max_length=160)
    context_code = models.CharField(max_length=80)
    idempotency_key = models.CharField(max_length=64, unique=True)
    message_id = models.CharField(max_length=160, unique=True)
    recipient_ciphertext = models.TextField()
    recipient_hmac = models.CharField(max_length=64)
    encryption_key_version = models.PositiveIntegerField()
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    delivery_phase = models.CharField(
        max_length=20,
        choices=DeliveryPhase.choices,
        default=DeliveryPhase.PRE_HANDOFF,
    )
    attempt_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    available_at = models.DateTimeField(default=timezone.now)
    claim_token = models.CharField(max_length=64, blank=True)
    claim_owner = models.CharField(max_length=120, blank=True)
    claim_generation = models.PositiveIntegerField(default=0)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    handoff_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    review_required_at = models.DateTimeField(null=True, blank=True)
    recipient_retention_deadline = models.DateTimeField()
    recipient_purged_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ("add", "change", "view")
        ordering = ("created_at", "notification_id")
        constraints = [
            models.CheckConstraint(
                condition=Q(max_attempts__gte=1, max_attempts__lte=10),
                name="notify_attempt_limit_valid",
            ),
            models.CheckConstraint(
                condition=Q(failure_count__lte=models.F("attempt_count")),
                name="notify_failures_lte_attempts",
            ),
            models.CheckConstraint(
                condition=(Q(recipient_purged_at__isnull=True) | Q(recipient_ciphertext="")),
                name="notify_purged_cipher_empty",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="running")
                    | (~Q(claim_token="") & ~Q(claim_owner="") & Q(lease_expires_at__isnull=False))
                ),
                name="notify_running_has_claim",
            ),
        ]
        indexes = [
            models.Index(fields=("status", "available_at"), name="notify_ready_idx"),
            models.Index(fields=("status", "lease_expires_at"), name="notify_lease_idx"),
            models.Index(
                fields=("recipient_purged_at", "recipient_retention_deadline"),
                name="notify_retention_idx",
            ),
            models.Index(fields=("account", "created_at"), name="notify_account_idx"),
        ]


class EncryptionKeyRotationJob(models.Model):
    """A fenced, resumable request to re-encrypt MFA authenticators."""

    class Purpose(models.TextChoices):
        MFA = "mfa", "MFA authenticator"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        RETRY_WAIT = "retry_wait", "Retry wait"
        COMPLETED = "completed", "Completed"
        FAILED_REVIEW = "failed_review", "Failed - review required"

    rotation_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purpose = models.CharField(max_length=24, choices=Purpose.choices, default=Purpose.MFA)
    source_key_version = models.PositiveIntegerField()
    target_key_version = models.PositiveIntegerField()
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING)
    available_at = models.DateTimeField(default=timezone.now)
    cursor_authenticator_id = models.PositiveBigIntegerField(null=True, blank=True)
    scanned_count = models.PositiveBigIntegerField(default=0)
    processed_count = models.PositiveBigIntegerField(default=0)
    attempt_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    claim_token = models.CharField(max_length=64, blank=True)
    claim_owner = models.CharField(max_length=120, blank=True)
    claim_generation = models.PositiveIntegerField(default=0)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    requested_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="requested_key_rotations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ("add", "change", "view")
        ordering = ("created_at", "rotation_id")
        constraints = [
            models.CheckConstraint(
                condition=~Q(source_key_version=models.F("target_key_version")),
                name="key_rotation_versions_differ",
            ),
            models.CheckConstraint(
                condition=Q(processed_count__lte=models.F("scanned_count")),
                name="key_rotation_processed_lte_scanned",
            ),
            models.CheckConstraint(
                condition=Q(max_attempts__gte=1, max_attempts__lte=10),
                name="key_rotation_attempt_limit",
            ),
            models.CheckConstraint(
                condition=Q(failure_count__lte=models.F("attempt_count")),
                name="key_rotation_failures_lte_attempts",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status="running")
                    | (~Q(claim_token="") & ~Q(claim_owner="") & Q(lease_expires_at__isnull=False))
                ),
                name="key_rotation_running_claimed",
            ),
            models.UniqueConstraint(
                fields=("purpose", "source_key_version", "target_key_version"),
                condition=Q(status__in=("pending", "running", "retry_wait")),
                name="unique_active_key_rotation",
            ),
        ]
        indexes = [
            models.Index(fields=("status", "available_at"), name="key_rotation_ready_idx"),
            models.Index(fields=("status", "lease_expires_at"), name="key_rotation_lease_idx"),
            models.Index(
                fields=("purpose", "source_key_version", "status"),
                name="key_rotation_source_idx",
            ),
        ]


class ImmutableSecurityEvidenceQuerySet(models.QuerySet):
    """Prevent mutable ORM operations against security-decision evidence."""

    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("security operation evidence is immutable")

    def delete(self) -> NoReturn:
        raise PermissionDenied("security operation evidence is immutable")


class ImmutableSecurityEvidence(models.Model):
    objects = ImmutableSecurityEvidenceQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise PermissionDenied("security operation evidence is immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("security operation evidence is immutable")


class PrivilegedInvitation(ImmutableSecurityEvidence):
    """Immutable evidence describing one privileged-role invitation."""

    request_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="privileged_invitations",
    )
    requested_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="requested_privileged_invitations",
    )
    role = models.CharField(max_length=40, choices=PrivilegedRoleAssignment.Role.choices)
    scope = models.CharField(max_length=20, choices=PrivilegedRoleAssignment.Scope.choices)
    organization = models.ForeignKey(
        "partners.PartnerOrganization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="privileged_invitations",
    )
    external_evidence_reference = models.CharField(max_length=120)
    secret_digest = models.CharField(max_length=64)
    subject_security_version = models.PositiveIntegerField()
    role_policy_version = models.PositiveSmallIntegerField(default=1)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        default_permissions = ("add", "view")
        ordering = ("-created_at", "request_id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(scope="platform", organization__isnull=True)
                    | Q(scope="organization", organization__isnull=False)
                ),
                name="valid_priv_invitation_scope",
            ),
        ]
        indexes = [
            models.Index(fields=("subject", "created_at"), name="priv_inv_subject_idx"),
            models.Index(fields=("expires_at",), name="priv_inv_expiry_idx"),
        ]

    @property
    def status(self) -> str:
        return self.operation_state.status


class PrivilegedInvitationState(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for acceptance"
        ACCEPTED = "accepted", "Accepted"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    invitation = models.OneToOneField(
        PrivilegedInvitation,
        on_delete=models.PROTECT,
        primary_key=True,
        related_name="operation_state",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    accepted_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancelled_privileged_invitations",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ("add", "change", "view")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(status="pending", accepted_at__isnull=True, cancelled_at__isnull=True)
                    | Q(status="accepted", accepted_at__isnull=False, cancelled_at__isnull=True)
                    | Q(status="cancelled", accepted_at__isnull=True, cancelled_at__isnull=False)
                    | Q(status="expired", accepted_at__isnull=True, cancelled_at__isnull=True)
                ),
                name="priv_invitation_state_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(cancelled_at__isnull=True, cancelled_by__isnull=True)
                    | Q(cancelled_at__isnull=False, cancelled_by__isnull=False)
                ),
                name="priv_invitation_cancel_actor",
            ),
        ]


class PrivilegedRecoveryRequest(ImmutableSecurityEvidence):
    """Immutable request evidence for the two-person factor recovery ceremony."""

    class Reason(models.TextChoices):
        LOST_FACTOR = "lost_factor", "Lost authenticator"
        REPLACED_DEVICE = "replaced_device", "Replaced device"
        FACTOR_COMPROMISE = "factor_compromise", "Possible factor compromise"

    request_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="privileged_recovery_requests",
    )
    requested_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="requested_privileged_recoveries",
    )
    external_evidence_reference = models.CharField(max_length=120)
    reason_code = models.CharField(max_length=32, choices=Reason.choices)
    subject_security_version = models.PositiveIntegerField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        default_permissions = ("add", "view")
        ordering = ("-created_at", "request_id")
        indexes = [
            models.Index(fields=("subject", "created_at"), name="priv_recovery_subject_idx"),
            models.Index(fields=("expires_at",), name="priv_recovery_expiry_idx"),
        ]

    @property
    def status(self) -> str:
        return self.operation_state.status


class PrivilegedRecoveryState(models.Model):
    class Status(models.TextChoices):
        PENDING_APPROVAL = "pending_approval", "Waiting for second approver"
        AWAITING_REENROLLMENT = "awaiting_reenrollment", "Waiting for MFA setup"
        COMPLETED = "completed", "Privileges restored"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    recovery = models.OneToOneField(
        PrivilegedRecoveryRequest,
        on_delete=models.PROTECT,
        primary_key=True,
        related_name="operation_state",
    )
    status = models.CharField(
        max_length=28,
        choices=Status.choices,
        default=Status.PENDING_APPROVAL,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    restored_at = models.DateTimeField(null=True, blank=True)
    restored_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="restored_privileged_recoveries",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ("add", "change", "view")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(status="pending_approval", approved_at__isnull=True, restored_at__isnull=True)
                    | Q(
                        status="awaiting_reenrollment",
                        approved_at__isnull=False,
                        restored_at__isnull=True,
                    )
                    | Q(
                        status="completed",
                        approved_at__isnull=False,
                        restored_at__isnull=False,
                        restored_by__isnull=False,
                    )
                    | Q(
                        status__in=("cancelled", "expired"),
                        restored_at__isnull=True,
                    )
                ),
                name="priv_recovery_state_valid",
            ),
        ]


class PrivilegedRecoveryApproval(ImmutableSecurityEvidence):
    approval_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recovery = models.OneToOneField(
        PrivilegedRecoveryRequest,
        on_delete=models.PROTECT,
        related_name="approval",
    )
    approved_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="approved_privileged_recoveries",
    )
    evidence_reference_digest = models.CharField(max_length=64)
    approved_subject_security_version = models.PositiveIntegerField()
    approved_at = models.DateTimeField(default=timezone.now)

    class Meta:
        default_permissions = ("add", "view")
        ordering = ("approved_at", "approval_id")


class PrivilegedRoleSuspension(models.Model):
    """Operational suspension preserving the underlying immutable assignment."""

    suspension_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(
        PrivilegedRoleAssignment,
        on_delete=models.PROTECT,
        related_name="recovery_suspensions",
    )
    recovery = models.ForeignKey(
        PrivilegedRecoveryRequest,
        on_delete=models.PROTECT,
        related_name="role_suspensions",
    )
    suspended_at = models.DateTimeField(default=timezone.now)
    restored_at = models.DateTimeField(null=True, blank=True)
    restored_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="restored_role_suspensions",
    )

    class Meta:
        default_permissions = ("add", "change", "view")
        ordering = ("suspended_at", "suspension_id")
        constraints = [
            models.UniqueConstraint(
                fields=("assignment",),
                condition=Q(restored_at__isnull=True),
                name="unique_active_role_suspension",
            ),
            models.CheckConstraint(
                condition=(
                    Q(restored_at__isnull=True, restored_by__isnull=True)
                    | Q(restored_at__isnull=False, restored_by__isnull=False)
                ),
                name="role_suspension_restore_actor",
            ),
        ]
