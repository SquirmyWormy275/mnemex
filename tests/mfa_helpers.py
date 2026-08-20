from __future__ import annotations

import time

from allauth.account.models import EmailAddress
from allauth.mfa.adapter import get_adapter as get_mfa_adapter
from allauth.mfa.models import Authenticator
from django.test import Client
from django.utils import timezone

from mnemex.accounts.allauth_bridge import replace_session_mfa_authentication
from mnemex.accounts.assurance import SESSION_SECURITY_VERSION_KEY
from mnemex.accounts.models import Account

SYNTHETIC_TOTP_SECRET = "JBSWY3DPEHPK3PXP"


def verify_account_email(account: Account) -> EmailAddress:
    if account.email_verified_at is None:
        account.email_verified_at = timezone.now()
        account.save(update_fields=["email_verified_at"])
    address, _created = EmailAddress.objects.update_or_create(
        user=account,
        email=account.email,
        defaults={"primary": True, "verified": True},
    )
    return address


def enroll_account_mfa(account: Account) -> Authenticator:
    """Create synthetic verified MFA evidence without performing an HTTP flow."""

    verify_account_email(account)
    if account.mfa_enrolled_at is None:
        account.mfa_enrolled_at = timezone.now()
        account.save(update_fields=["mfa_enrolled_at"])
    authenticator, _created = Authenticator.objects.get_or_create(
        user=account,
        type=Authenticator.Type.TOTP,
        defaults={"data": {"secret": get_mfa_adapter().encrypt(SYNTHETIC_TOTP_SECRET)}},
    )
    return authenticator


def force_login_with_fresh_mfa(client: Client, account: Account) -> Authenticator:
    authenticator = enroll_account_mfa(account)
    client.force_login(account)
    session = client.session
    session[SESSION_SECURITY_VERSION_KEY] = account.security_version
    replace_session_mfa_authentication(session, authenticator, verified_at=time.time())
    session.save()
    return authenticator
