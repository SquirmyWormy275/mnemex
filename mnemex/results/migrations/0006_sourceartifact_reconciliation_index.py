from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("results", "0005_artifactobject_artifactobjectwrite"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="sourceartifact",
            index=models.Index(
                fields=[
                    "object_reference",
                    "digest",
                    "byte_size",
                    "received_at",
                    "artifact_id",
                ],
                name="artifact_source_lookup_idx",
            ),
        ),
    ]
