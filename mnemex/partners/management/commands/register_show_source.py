"""Explicit sandbox administration; credentials go only to a new private file."""

import hashlib
import json
import os
import secrets
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from mnemex.partners.models import PartnerClient, ShowClientCredential, ShowSource
from mnemex.partners.show_results import reference


class Command(BaseCommand):
    help = (
        "Register a synthetic sandbox source and write a scoped credential to a new private file."
    )

    def add_arguments(self, parser):
        parser.add_argument("--client", required=True)
        parser.add_argument("--source-show-id", required=True)
        parser.add_argument("--credential-output", required=True, type=Path)

    @transaction.atomic
    def handle(self, *args, **options):
        client = PartnerClient.objects.select_for_update().get(pk=options["client"])
        if not client.is_active or client.environment != "sandbox":
            raise CommandError("Only active synthetic sandbox clients are supported.")
        reference(options["source_show_id"])
        target = options["credential_output"]
        if not target.is_absolute() or target.exists():
            raise CommandError("Credential output must be a new absolute private file.")
        source, _ = ShowSource.objects.get_or_create(
            source_show_id=options["source_show_id"], defaults={"client": client}
        )
        if source.client_id != client.pk:
            raise CommandError("Source is registered to another client.")
        token = secrets.token_urlsafe(48)
        ShowClientCredential.objects.create(
            client=client,
            source_show_id=source.pk,
            token_sha256=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=timezone.now() + timedelta(days=1),
        )
        with target.open("x") as output:
            if os.name != "nt":
                os.fchmod(output.fileno(), 0o600)
            json.dump({"source_show_id": source.pk, "token": token}, output)
        self.stdout.write(
            "Sandbox source credential written to the private destination; production remains disabled."
        )
