from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_privilegedroleassignment"),
        ("partners", "0001_initial"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="privilegedroleassignment",
            name="unique_active_privileged_role",
        ),
        migrations.AddField(
            model_name="privilegedroleassignment",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="privileged_role_assignments",
                to="partners.partnerorganization",
            ),
        ),
        migrations.AddField(
            model_name="privilegedroleassignment",
            name="scope",
            field=models.CharField(
                choices=[("platform", "Platform wide"), ("organization", "Partner organization")],
                default="platform",
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="privilegedroleassignment",
            index=models.Index(
                fields=["role", "scope", "organization", "revoked_at"],
                name="role_scope_active_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="privilegedroleassignment",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("organization__isnull", True), ("scope", "platform"))
                    | models.Q(("organization__isnull", False), ("scope", "organization"))
                ),
                name="valid_priv_role_scope",
            ),
        ),
        migrations.AddConstraint(
            model_name="privilegedroleassignment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("revoked_at__isnull", True), ("scope", "platform")),
                fields=("account", "role"),
                name="unique_active_platform_role",
            ),
        ),
        migrations.AddConstraint(
            model_name="privilegedroleassignment",
            constraint=models.UniqueConstraint(
                condition=models.Q(("revoked_at__isnull", True), ("scope", "organization")),
                fields=("account", "role", "organization"),
                name="unique_active_org_role",
            ),
        ),
    ]
