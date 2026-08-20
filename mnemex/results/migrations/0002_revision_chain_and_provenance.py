import hashlib
import json

import django.db.models.deletion
from django.db import migrations, models


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def backfill_provenance_and_revision_chain(apps, schema_editor):
    MappingTemplate = apps.get_model("results", "MappingTemplate")
    IngestionRun = apps.get_model("results", "IngestionRun")
    PublishedSourceResult = apps.get_model("results", "PublishedSourceResult")

    mapping_digests = {
        str(template_id): _digest(field_map)
        for template_id, field_map in MappingTemplate.objects.values_list(
            "template_id", "field_map"
        )
    }
    for run in IngestionRun.objects.only("run_id", "mapping_template_id"):
        run.field_map_digest = mapping_digests.get(str(run.mapping_template_id), "")
        run.save(update_fields=["field_map_digest"])

    previous_by_source = {}
    results = PublishedSourceResult.objects.order_by(
        "organization_id", "source_result_id", "source_revision", "published_result_id"
    ).only(
        "published_result_id",
        "organization_id",
        "source_result_id",
        "source_revision",
    )
    for result in results:
        source_key = (result.organization_id, result.source_result_id)
        previous = previous_by_source.get(source_key)
        if previous is None and result.source_revision != 1:
            raise RuntimeError(
                "cannot migrate a source-result revision chain that does not begin at revision 1"
            )
        if previous is not None and previous.source_revision + 1 != result.source_revision:
            raise RuntimeError("cannot migrate a noncontiguous source-result revision chain")
        if previous is not None:
            result.predecessor_id = previous.published_result_id
            result.save(update_fields=["predecessor"])
        previous_by_source[source_key] = result


class Migration(migrations.Migration):
    dependencies = [("results", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="ingestionrun",
            name="field_map_digest",
            field=models.CharField(default="", max_length=64),
        ),
        migrations.AddField(
            model_name="publishedsourceresult",
            name="predecessor",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="successor",
                to="results.publishedsourceresult",
            ),
        ),
        migrations.RunPython(
            backfill_provenance_and_revision_chain,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="publishedsourceresult",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("source_revision__gte", 1),
                    ("source_revision__lte", 2_147_483_647),
                ),
                name="published_source_revision_range",
            ),
        ),
    ]
