from __future__ import annotations

from unittest.mock import patch

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.adapter import get_adapter as get_mfa_adapter
from allauth.mfa.models import Authenticator
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.utils import timezone

from mnemex.accounts.key_rotation import enqueue_mfa_key_rotation
from mnemex.accounts.models import Account, EncryptionKeyRotationJob
from mnemex.accounts.notifications import (
    claim_next_notification,
    enqueue_security_notification,
    mark_notification_handoff,
    settle_notification_delivery_uncertain,
)
from mnemex.supervisor import QueueTask, run_supervisor
from mnemex.worker import main as worker_main


def test_supervisor_rotates_first_queue_without_starving_siblings() -> None:
    calls: list[str] = []
    tasks = [
        QueueTask(name=name, run=lambda name=name: calls.append(name))
        for name in ("artifacts", "migrations", "notifications", "key_rotation")
    ]

    outcome = run_supervisor(
        tasks=tasks,
        should_stop=lambda: False,
        sleep=lambda _seconds: None,
        jitter=lambda _low, _high: 0.0,
        max_cycles=4,
    )

    assert outcome.cycles == 4
    assert outcome.task_runs == 16
    assert outcome.unhealthy is False
    assert calls == [
        "artifacts",
        "migrations",
        "notifications",
        "key_rotation",
        "migrations",
        "notifications",
        "key_rotation",
        "artifacts",
        "notifications",
        "key_rotation",
        "artifacts",
        "migrations",
        "key_rotation",
        "artifacts",
        "migrations",
        "notifications",
    ]


def test_supervisor_stops_before_claim_and_between_tasks() -> None:
    calls: list[str] = []
    stop_checks = iter((False, False, True))

    outcome = run_supervisor(
        tasks=(
            QueueTask(name="first", run=lambda: calls.append("first")),
            QueueTask(name="second", run=lambda: calls.append("second")),
        ),
        should_stop=lambda: next(stop_checks, True),
        sleep=lambda _seconds: None,
        jitter=lambda _low, _high: 0.0,
    )

    assert calls == ["first"]
    assert outcome.stopped is True
    assert outcome.task_runs == 1


def test_one_failing_queue_does_not_starve_healthy_work() -> None:
    calls: list[str] = []
    observations: list[tuple[str, str, str]] = []

    def fail() -> None:
        raise RuntimeError("secret provider response must not be logged")

    outcome = run_supervisor(
        tasks=(
            QueueTask(name="failing", run=fail, unhealthy_after=2),
            QueueTask(name="healthy", run=lambda: calls.append("healthy")),
        ),
        should_stop=lambda: False,
        sleep=lambda _seconds: None,
        jitter=lambda _low, _high: 0.0,
        observe=lambda event, task, code: observations.append((event, task, code)),
        max_cycles=3,
    )

    assert calls == ["healthy", "healthy"]
    assert outcome.unhealthy is True
    assert outcome.failure_count == 2
    assert observations == [
        ("task_failed", "failing", "RuntimeError"),
        ("task_failed", "failing", "RuntimeError"),
    ]
    assert "secret" not in repr(observations)


def test_idle_delay_is_bounded_and_injected() -> None:
    sleeps: list[float] = []

    outcome = run_supervisor(
        tasks=(QueueTask(name="idle", run=lambda: None),),
        should_stop=lambda: False,
        sleep=sleeps.append,
        jitter=lambda low, high: (low + high) / 2,
        idle_seconds=5.0,
        jitter_seconds=1.0,
        max_cycles=2,
    )

    assert outcome.cycles == 2
    assert sleeps == [5.0]


def test_supervisor_rejects_invalid_configuration() -> None:
    def noop() -> None:
        pass

    for tasks, idle, jitter_seconds in (
        ((), 5.0, 1.0),
        ((QueueTask(name="x", run=noop), QueueTask(name="x", run=noop)), 5.0, 1.0),
        ((QueueTask(name="x", run=noop),), 0.0, 1.0),
        ((QueueTask(name="x", run=noop),), 5.0, -1.0),
    ):
        try:
            run_supervisor(
                tasks=tasks,
                should_stop=lambda: True,
                sleep=lambda _seconds: None,
                jitter=lambda _low, _high: 0.0,
                idle_seconds=idle,
                jitter_seconds=jitter_seconds,
            )
        except ValueError:
            continue
        raise AssertionError("invalid supervisor configuration was accepted")


@override_settings(MNEMEX_PRIVATE_ARTIFACT_BACKEND="local")
@pytest.mark.django_db
def test_worker_supervise_runs_bounded_fair_domain_tasks(tmp_path, capsys, settings) -> None:
    settings.MNEMEX_PRIVATE_ARTIFACT_ROOT = tmp_path / "private"

    result = worker_main(
        ["--supervise"],
        worker_owner="synthetic-supervisor",
        supervisor_max_cycles=1,
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "supervisor" in output
    assert "artifact_reconciliation" in output
    assert "migration_apply" in output
    assert "security_notifications" in output
    assert "mfa_key_rotation" in output
    for task in ("artifact_reconciliation", "migration_apply", "mfa_key_rotation"):
        line = next(item for item in output.splitlines() if f"task={task}" in item)
        assert "ready=0" in line
        assert "oldest_ready_age_seconds=None" in line
    assert "http://" not in output
    assert "@" not in output


@override_settings(MNEMEX_PRIVATE_ARTIFACT_BACKEND="local")
@pytest.mark.django_db
def test_worker_supervise_keeps_other_queues_alive_for_persistent_mail_review(
    tmp_path,
    capsys,
    settings,
) -> None:
    settings.MNEMEX_PRIVATE_ARTIFACT_ROOT = tmp_path / "private"
    account = Account.objects.create_user(
        email="uncertain-notification@mnemex.example.invalid",
        password=None,
        email_verified_at=timezone.now(),
    )
    EmailAddress.objects.create(
        user=account,
        email=account.email,
        primary=True,
        verified=True,
    )
    enqueue_security_notification(
        account=account,
        template_identifier="mfa/email/totp_activated",
        recipient=account.email,
        context_code="account-security-v1",
        idempotency_key="persistent-review-supervisor",
    )
    claim = claim_next_notification(owner="synthetic-mail-review")
    assert claim is not None
    mark_notification_handoff(claim)
    settle_notification_delivery_uncertain(claim)

    from mnemex.supervisor import run_supervisor as real_run_supervisor

    def run_without_sleep(**kwargs):
        return real_run_supervisor(
            **kwargs,
            sleep=lambda _seconds: None,
            jitter=lambda _low, _high: 0.0,
        )

    with patch("mnemex.supervisor.run_supervisor", side_effect=run_without_sleep):
        result = worker_main(
            ["--supervise"],
            worker_owner="synthetic-supervisor",
            supervisor_max_cycles=5,
        )

    assert result == 0
    output = capsys.readouterr().out
    assert "delivery_uncertain=1" in output
    assert "unhealthy=0" in output


@override_settings(
    MNEMEX_PRIVATE_ARTIFACT_BACKEND="local",
    MNEMEX_MFA_ENCRYPTION_KEYS={
        1: bytes(range(32)),
        2: bytes(range(32, 64)),
    },
    MNEMEX_MFA_ACTIVE_KEY_VERSION=2,
)
@pytest.mark.django_db
def test_worker_supervise_executes_one_bounded_mfa_rotation(
    tmp_path,
    capsys,
    settings,
) -> None:
    settings.MNEMEX_PRIVATE_ARTIFACT_ROOT = tmp_path / "private"
    account = Account.objects.create_user(
        email="rotation-supervisor@example.invalid",
        password=None,
        email_verified_at=timezone.now(),
    )
    with override_settings(MNEMEX_MFA_ACTIVE_KEY_VERSION=1):
        authenticator = Authenticator.objects.create(
            user=account,
            type=Authenticator.Type.TOTP,
            data={"secret": get_mfa_adapter().encrypt("synthetic-supervisor-secret")},
        )
    job = enqueue_mfa_key_rotation(
        requested_by=account,
        source_version=1,
        target_version=2,
    )

    result = worker_main(
        ["--supervise"],
        worker_owner="synthetic-supervisor",
        supervisor_max_cycles=1,
    )

    job.refresh_from_db()
    authenticator.refresh_from_db()
    assert result == 0
    assert job.status == EncryptionKeyRotationJob.Status.COMPLETED
    assert authenticator.data["secret"].startswith("v2.")
    output = capsys.readouterr().out
    assert "worker task=mfa_key_rotation claimed=1" in output
    assert "synthetic-supervisor-secret" not in output


@override_settings(MNEMEX_PRIVATE_ARTIFACT_BACKEND="local")
@pytest.mark.django_db
def test_worker_supervise_refuses_missing_historical_key_version(
    tmp_path,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.MNEMEX_PRIVATE_ARTIFACT_ROOT = tmp_path / "private"

    def fail_key_check(*, purpose: str) -> None:
        raise ImproperlyConfigured(f"required {purpose} encryption key is unavailable")

    monkeypatch.setattr(
        "mnemex.accounts.key_rotation.assert_configured_key_versions_available",
        fail_key_check,
    )

    with pytest.raises(ImproperlyConfigured, match="required mfa encryption key"):
        worker_main(
            ["--supervise"],
            worker_owner="synthetic-supervisor",
            supervisor_max_cycles=1,
        )
