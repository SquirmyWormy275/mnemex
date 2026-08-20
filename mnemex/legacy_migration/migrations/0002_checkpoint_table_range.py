from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("legacy_migration", "0001_initial")]

    operations = [
        migrations.RemoveConstraint(
            model_name="legacymigrationcheckpoint",
            name="uniq_legacy_checkpoint_range",
        ),
        migrations.AddConstraint(
            model_name="legacymigrationcheckpoint",
            constraint=models.UniqueConstraint(
                fields=("run", "table_plan", "first_source_row", "last_source_row"),
                name="uniq_legacy_checkpoint_table_range",
            ),
        ),
    ]
