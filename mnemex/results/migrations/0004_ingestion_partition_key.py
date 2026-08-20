from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("results", "0003_spreadsheet_source_coordinates")]

    operations = [
        migrations.AddField(
            model_name="ingestionrun",
            name="source_partition_key",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.RemoveConstraint(
            model_name="ingestionrun",
            name="unique_artifact_mapping_sheet_ingestion",
        ),
        migrations.AddConstraint(
            model_name="ingestionrun",
            constraint=models.UniqueConstraint(
                fields=(
                    "artifact",
                    "mapping_template",
                    "source_sheet_name",
                    "source_partition_key",
                ),
                name="unique_artifact_map_sheet_partition",
            ),
        ),
    ]
