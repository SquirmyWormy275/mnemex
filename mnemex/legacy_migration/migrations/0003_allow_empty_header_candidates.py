from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("legacy_migration", "0002_checkpoint_table_range")]

    operations = [
        migrations.AlterField(
            model_name="legacyworksheetplan",
            name="header_candidates",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
