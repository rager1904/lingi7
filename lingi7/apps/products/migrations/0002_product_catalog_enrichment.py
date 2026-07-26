# Generated manually for catalog enrichment Phase 1

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="enrichment_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Not enriched"),
                    ("PROCESSING", "Enrichment in progress"),
                    ("COMPLETED", "Enrichment complete"),
                    ("FAILED", "Enrichment failed"),
                    ("DISABLED", "Enrichment disabled"),
                ],
                db_index=True,
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="enriched_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="enrichment_error",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="product",
            name="meta_title",
            field=models.CharField(blank=True, max_length=70),
        ),
        migrations.AddField(
            model_name="product",
            name="meta_description",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="product",
            name="search_keywords",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="product",
            name="ai_enhanced_title",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="product",
            name="ai_features",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="product",
            name="ai_specs",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="product",
            name="suggested_category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="suggested_for_products",
                to="products.category",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="suggested_tags",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="product",
            name="image_quality_scores",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="product",
            name="descriptions_i18n",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
