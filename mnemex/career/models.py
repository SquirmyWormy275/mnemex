from __future__ import annotations

import uuid
from typing import Any, NoReturn

from django.core.exceptions import PermissionDenied
from django.db import models

from mnemex.accounts.models import Account
from mnemex.consent.models import ConsentGrant
from mnemex.partners.models import PartnerOrganization
from mnemex.people.models import Person
from mnemex.results.models import PublishedSourceResult, ReconciliationCase


class ImmutableCareerAssertionQuerySet(models.QuerySet["CareerAssertionRevision"]):
    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("career assertion revisions are immutable")

    def delete(self) -> NoReturn:
        raise PermissionDenied("career assertion revisions are immutable")


class CareerAssertionRevision(models.Model):
    """An immutable reviewed link between a source result and a MNEMEX person.

    Corrections append a successor. A revision is current exactly while no
    successor points to it; superseding never requires changing the prior row.
    """

    class Decision(models.TextChoices):
        APPROVE_LINK = "approve_link", "Approve identity link"
        RELINK = "relink", "Correct identity link"

    class AuthorizationBasis(models.TextChoices):
        COMPETITOR_CONSENT = "competitor_consent", "Competitor consent"
        GUARDIAN_CONSENT = "guardian_consent", "Guardian consent"
        SOURCE_DATA_RIGHTS = "source_data_rights", "Source data rights"
        SHOW_FINALIZATION_POLICY = (
            "show_finalization_policy",
            "Show finalization policy",
        )

    assertion_revision_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        PartnerOrganization,
        on_delete=models.PROTECT,
        related_name="career_assertion_revisions",
    )
    source_result = models.ForeignKey(
        PublishedSourceResult,
        on_delete=models.PROTECT,
        related_name="career_assertion_revisions",
    )
    person = models.ForeignKey(
        Person,
        on_delete=models.PROTECT,
        related_name="career_assertion_revisions",
    )
    reconciliation_case = models.ForeignKey(
        ReconciliationCase,
        on_delete=models.PROTECT,
        related_name="career_assertion_revisions",
    )
    revision = models.PositiveIntegerField()
    predecessor = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        related_name="successor",
        null=True,
        blank=True,
    )
    decision = models.CharField(max_length=24, choices=Decision.choices)
    authorization_basis_type = models.CharField(max_length=40, choices=AuthorizationBasis.choices)
    authorization_basis_reference = models.CharField(max_length=240)
    consent_grant = models.ForeignKey(
        ConsentGrant,
        on_delete=models.PROTECT,
        related_name="career_assertion_revisions",
        null=True,
        blank=True,
    )
    authorization_captured_at = models.DateTimeField()
    reviewed_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="reviewed_career_assertion_revisions",
    )
    source_payload_digest = models.CharField(max_length=64)
    decision_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableCareerAssertionQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(revision__gte=1), name="career_revision_positive"
            ),
            models.UniqueConstraint(
                fields=("source_result", "revision"), name="unique_career_source_revision"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        authorization_basis_type__in=(
                            "competitor_consent",
                            "guardian_consent",
                        ),
                        consent_grant__isnull=False,
                    )
                    | models.Q(
                        authorization_basis_type__in=(
                            "source_data_rights",
                            "show_finalization_policy",
                        ),
                        consent_grant__isnull=True,
                    )
                ),
                name="career_authority_evidence_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("organization", "source_result", "revision"),
                name="career_source_revision_idx",
            ),
            models.Index(fields=("person", "created_at"), name="career_person_history_idx"),
        ]

    @property
    def is_current(self) -> bool:
        return not type(self).objects.filter(predecessor_id=self.pk).exists()

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise PermissionDenied("career assertion revisions are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("career assertion revisions are immutable")
