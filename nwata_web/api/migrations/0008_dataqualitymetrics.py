# Generated migration for DataQualityMetrics model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0007_data_quality_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="DataQualityMetrics",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("date", models.DateField(db_index=True)),
                ("total_logs", models.IntegerField(default=0)),
                ("valid_logs", models.IntegerField(default=0)),
                ("schema_violations", models.IntegerField(default=0)),
                ("avg_data_quality_score", models.FloatField(default=0.0)),
                ("min_data_quality_score", models.FloatField(default=0.0)),
                ("max_data_quality_score", models.FloatField(default=1.0)),
                ("logs_with_context", models.IntegerField(default=0)),
                ("avg_idle_ratio", models.FloatField(default=0.0)),
                ("avg_typing_rate_per_min", models.FloatField(default=0.0)),
                ("avg_activity_intensity", models.FloatField(default=0.0)),
                ("quality_degradation_flag", models.BooleanField(default=False)),
                ("high_violation_rate_flag", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="quality_metrics",
                        to="api.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["-date"],
            },
        ),
        migrations.AddConstraint(
            model_name="dataqualitymetrics",
            constraint=models.UniqueConstraint(
                fields=["date", "organization"],
                name="unique_daily_org_quality",
            ),
        ),
        migrations.AddIndex(
            model_name="dataqualitymetrics",
            index=models.Index(
                fields=["date", "organization"],
                name="api_dataqua_date_org_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="dataqualitymetrics",
            index=models.Index(
                fields=["organization", "date"],
                name="api_dataqua_org_date_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="dataqualitymetrics",
            index=models.Index(
                fields=["updated_at"],
                name="api_dataqua_updated_idx",
            ),
        ),
    ]
