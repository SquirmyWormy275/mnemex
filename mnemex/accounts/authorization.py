from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from django.conf import settings
from django.db.models import Q, QuerySet

from mnemex.accounts.models import (
    Account,
    PrivilegedRoleAssignment,
    PrivilegedRoleSuspension,
)

if TYPE_CHECKING:
    from mnemex.partners.models import PartnerOrganization
    from mnemex.people.models import GuardianRelationship, Person


class Action(str, Enum):
    MANAGE_OWN_PROFILE = "manage_own_profile"
    MANAGE_GUARDIAN_PROFILE = "manage_guardian_profile"
    MANAGE_RESULTS = "manage_results"
    REVIEW_EXPORT = "review_export"
    REVIEW_IDENTITY = "review_identity"
    RUN_PRIVACY_WORKFLOW = "run_privacy_workflow"
    ADMINISTER_PARTNER = "administer_partner"
    MANAGE_SECURITY_OPERATIONS = "manage_security_operations"


_ROLE_ACTIONS = {
    Action.MANAGE_RESULTS: PrivilegedRoleAssignment.Role.RESULTS_MANAGER,
    Action.REVIEW_EXPORT: PrivilegedRoleAssignment.Role.EXPORT_REVIEWER,
    Action.REVIEW_IDENTITY: PrivilegedRoleAssignment.Role.IDENTITY_REVIEWER,
    Action.RUN_PRIVACY_WORKFLOW: PrivilegedRoleAssignment.Role.PRIVACY_OFFICER,
    Action.ADMINISTER_PARTNER: PrivilegedRoleAssignment.Role.PARTNER_ADMINISTRATOR,
    Action.MANAGE_SECURITY_OPERATIONS: PrivilegedRoleAssignment.Role.SECURITY_ADMINISTRATOR,
}


def _current_account(account: Account) -> Account | None:
    # Enrollment metadata is not proof that this session completed MFA. Keep
    # every privileged action disabled unless an environment-specific settings
    # module explicitly enables the pilot-only authorization path.
    if not getattr(settings, "MNEMEX_PRIVILEGED_AUTHORIZATION_ENABLED", False):
        return None
    current_account = Account.objects.filter(pk=account.pk).first()
    if (
        current_account is None
        or not current_account.is_active
        or current_account.email_verified_at is None
        or current_account.mfa_enrolled_at is None
    ):
        return None
    # Background jobs have no browser session, but they still require a real,
    # current authenticator rather than trusting the historical timestamp.
    from allauth.account.models import EmailAddress
    from allauth.mfa.models import Authenticator

    if not EmailAddress.objects.filter(
        user=current_account,
        email__iexact=current_account.email,
        verified=True,
    ).exists():
        return None
    if not Authenticator.objects.filter(
        user=current_account,
        type=Authenticator.Type.TOTP,
    ).exists():
        return None
    return current_account


def has_effective_role(
    account: Account,
    role: PrivilegedRoleAssignment.Role | str,
    *,
    organization: PartnerOrganization | None = None,
) -> bool:
    """Return whether an MFA-bound role covers the requested tenant.

    Omitting ``organization`` deliberately checks platform-wide scope only. This
    keeps historical assignments safe after migration without letting an
    organization assignment silently become global.
    """

    current_account = _current_account(account)
    if current_account is None:
        return False
    assignments = current_account.privileged_roles.filter(
        role=role,
        revoked_at__isnull=True,
    ).exclude(
        pk__in=PrivilegedRoleSuspension.objects.filter(restored_at__isnull=True).values(
            "assignment_id"
        )
    )
    if organization is None:
        return assignments.filter(
            scope=PrivilegedRoleAssignment.Scope.PLATFORM,
            organization__isnull=True,
        ).exists()
    from mnemex.partners.models import PartnerOrganization

    current_organization = PartnerOrganization.objects.filter(
        pk=organization.pk, status=PartnerOrganization.Status.ACTIVE
    ).first()
    if current_organization is None:
        return False
    return assignments.filter(
        Q(scope=PrivilegedRoleAssignment.Scope.PLATFORM, organization__isnull=True)
        | Q(
            scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
            organization_id=current_organization.pk,
        )
    ).exists()


def organizations_for_action(account: Account, action: Action) -> QuerySet[PartnerOrganization]:
    """Return active organizations explicitly covered by an effective role."""

    from mnemex.partners.models import PartnerOrganization

    required_role = _ROLE_ACTIONS.get(action)
    current_account = _current_account(account)
    if required_role is None or current_account is None:
        return PartnerOrganization.objects.none()
    assignments = current_account.privileged_roles.filter(
        role=required_role, revoked_at__isnull=True
    ).exclude(
        pk__in=PrivilegedRoleSuspension.objects.filter(restored_at__isnull=True).values(
            "assignment_id"
        )
    )
    if assignments.filter(
        scope=PrivilegedRoleAssignment.Scope.PLATFORM,
        organization__isnull=True,
    ).exists():
        return PartnerOrganization.objects.filter(status=PartnerOrganization.Status.ACTIVE)
    organization_ids = assignments.filter(
        scope=PrivilegedRoleAssignment.Scope.ORGANIZATION,
        organization__isnull=False,
    ).values("organization_id")
    return PartnerOrganization.objects.filter(
        status=PartnerOrganization.Status.ACTIVE,
        organization_id__in=organization_ids,
    )


def may_perform(
    account: Account,
    action: Action,
    *,
    person: Person | None = None,
    guardian_relationship: GuardianRelationship | None = None,
    organization: PartnerOrganization | None = None,
) -> bool:
    from mnemex.people.models import GuardianRelationship, Person

    current_account = Account.objects.filter(pk=account.pk).first()
    if current_account is None or not current_account.is_active:
        return False
    if action == Action.MANAGE_OWN_PROFILE:
        if person is None:
            return False
        current_person = Person.objects.filter(pk=person.pk).first()
        return (
            current_person is not None
            and current_person.status == Person.Status.ACTIVE
            and current_person.account_id == current_account.account_id
        )
    if action == Action.MANAGE_GUARDIAN_PROFILE:
        if person is None or guardian_relationship is None:
            return False
        current_person = Person.objects.filter(pk=person.pk).first()
        current_relationship = GuardianRelationship.objects.filter(
            pk=guardian_relationship.pk
        ).first()
        return (
            current_person is not None
            and current_relationship is not None
            and current_person.status == Person.Status.ACTIVE
            and current_relationship.guardian_account_id == current_account.account_id
            and current_relationship.minor_person_id == current_person.person_id
            and current_relationship.is_active
        )
    required_role = _ROLE_ACTIONS.get(action)
    return required_role is not None and has_effective_role(
        current_account, required_role, organization=organization
    )
