from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("results", "0002_revision_chain_and_provenance")]

    operations = [
        migrations.AddField(
            model_name="ingestionrun",
            name="source_sheet_name",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="stagedresult",
            name="source_row_number",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="stagedresult",
            name="source_sheet_name",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.RemoveConstraint(
            model_name="ingestionrun",
            name="unique_artifact_mapping_ingestion",
        ),
        migrations.AddConstraint(
            model_name="ingestionrun",
            constraint=models.UniqueConstraint(
                fields=("artifact", "mapping_template", "source_sheet_name"),
                name="unique_artifact_mapping_sheet_ingestion",
            ),
        ),
    ]
