# Generated for the SeenByAI MVP.
import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Visitor",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("cookie_token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("ip_hash", models.CharField(blank=True, max_length=64)),
                ("user_agent_hash", models.CharField(blank=True, max_length=64)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("free_audits_used", models.PositiveSmallIntegerField(default=0)),
                ("paid_audit_credits", models.PositiveIntegerField(default=0)),
                ("first_seen_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-last_seen_at"],
            },
        ),
        migrations.CreateModel(
            name="AuditReport",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("url", models.URLField(max_length=500)),
                ("domain", models.CharField(max_length=255)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("running", "Running"), ("complete", "Complete"), ("failed", "Failed")], default="pending", max_length=20)),
                ("credit_type", models.CharField(choices=[("free", "Free"), ("paid", "Paid")], default="free", max_length=20)),
                ("credit_refunded", models.BooleanField(default=False)),
                ("overall_score", models.FloatField(blank=True, null=True)),
                ("score_grade", models.CharField(blank=True, max_length=2)),
                ("score_technical", models.FloatField(blank=True, null=True)),
                ("score_schema", models.FloatField(blank=True, null=True)),
                ("score_eeat", models.FloatField(blank=True, null=True)),
                ("score_content", models.FloatField(blank=True, null=True)),
                ("score_authority", models.FloatField(blank=True, null=True)),
                ("crawl_data", models.JSONField(default=dict)),
                ("schema_data", models.JSONField(default=dict)),
                ("citation_data", models.JSONField(default=dict)),
                ("technical_data", models.JSONField(default=dict)),
                ("error_message", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("visitor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="audits", to="audits.visitor")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AuditFinding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dimension", models.CharField(max_length=30)),
                ("severity", models.CharField(choices=[("critical", "Critical"), ("high", "High"), ("medium", "Medium"), ("low", "Low"), ("pass", "Pass")], max_length=20)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField()),
                ("recommendation", models.TextField(blank=True)),
                ("points_impact", models.FloatField(default=0)),
                ("is_passed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("audit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="findings", to="audits.auditreport")),
            ],
            options={
                "ordering": ["dimension", "is_passed", "points_impact"],
            },
        ),
        migrations.CreateModel(
            name="CitationCheck",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ai_engine", models.CharField(max_length=50)),
                ("query_used", models.TextField()),
                ("status", models.CharField(choices=[("complete", "Complete"), ("skipped", "Skipped"), ("failed", "Failed")], default="complete", max_length=20)),
                ("was_cited", models.BooleanField(default=False)),
                ("citation_url", models.URLField(blank=True)),
                ("ai_response_snippet", models.TextField(blank=True)),
                ("all_citations", models.JSONField(default=list)),
                ("checked_at", models.DateTimeField(auto_now_add=True)),
                ("audit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="citation_checks", to="audits.auditreport")),
            ],
            options={
                "ordering": ["ai_engine", "query_used"],
            },
        ),
        migrations.AddIndex(
            model_name="auditreport",
            index=models.Index(fields=["visitor", "-created_at"], name="audits_audi_visitor_15d763_idx"),
        ),
        migrations.AddIndex(
            model_name="auditreport",
            index=models.Index(fields=["domain"], name="audits_audi_domain_7b7d9d_idx"),
        ),
        migrations.AddIndex(
            model_name="auditreport",
            index=models.Index(fields=["status"], name="audits_audi_status_614d09_idx"),
        ),
    ]
