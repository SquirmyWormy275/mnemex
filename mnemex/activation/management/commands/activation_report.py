from __future__ import annotations

from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from mnemex.accounts.key_rotation import assert_configured_key_versions_available

from ...models import ActivationEvidence
from ...report import (
    ACTIVATION_GATES,
    build_activation_report,
    canonical_report_json,
    compute_environment_fingerprint,
    select_latest_evidence,
)


class Command(BaseCommand):
    help = "Render a redacted, fail-closed activation diagnostic report"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--environment",
            choices=("local", "staging", "production"),
            required=True,
        )
        parser.add_argument("--release-digest", required=True)
        parser.add_argument("--configuration-digest", required=True)
        parser.add_argument(
            "--format",
            dest="output_format",
            choices=("human", "json"),
            default="human",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            assert_configured_key_versions_available(purpose="mfa")
            assert_configured_key_versions_available(purpose="notification")
        except ImproperlyConfigured as error:
            raise CommandError("required encryption key is unavailable") from error
        fingerprint = compute_environment_fingerprint(
            environment=options["environment"],
            release_digest=options["release_digest"],
            configuration_digest=options["configuration_digest"],
        )
        records = select_latest_evidence(
            ActivationEvidence.objects.filter(environment_fingerprint=fingerprint)
        )
        report = build_activation_report(
            records,
            environment=options["environment"],
            environment_fingerprint=fingerprint,
            generated_at=timezone.now(),
        )
        if options["output_format"] == "json":
            self.stdout.write(canonical_report_json(report))
            return

        self.stdout.write(f"Decision: {report['decision']}")
        self.stdout.write("Production privilege: hard_disabled")
        self.stdout.write(f"Environment fingerprint: {report['environment_fingerprint']}")
        for gate_id in ACTIVATION_GATES:
            gate = next(item for item in report["gates"] if item["gate_id"] == gate_id)
            self.stdout.write(f"{gate_id}: {gate['result']} ({gate['reason']})")
