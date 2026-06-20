from django.db import migrations, models
import django.db.models.deletion


def migrate_existing_visitors(apps, schema_editor):
    Customer = apps.get_model("audits", "Customer")
    Visitor = apps.get_model("audits", "Visitor")
    AuditReport = apps.get_model("audits", "AuditReport")

    for visitor in Visitor.objects.exclude(email=""):
        email = visitor.email.strip().lower()
        if not email:
            continue
        customer, _ = Customer.objects.get_or_create(email=email)
        customer.free_audits_used += visitor.free_audits_used
        customer.paid_audit_credits += visitor.paid_audit_credits
        customer.save(update_fields=["free_audits_used", "paid_audit_credits", "updated_at"])
        AuditReport.objects.filter(visitor=visitor, customer__isnull=True).update(customer=customer)


class Migration(migrations.Migration):
    dependencies = [
        ("audits", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Customer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("free_audits_used", models.PositiveSmallIntegerField(default=0)),
                ("paid_audit_credits", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["email"],
            },
        ),
        migrations.AddField(
            model_name="auditreport",
            name="customer",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="audits", to="audits.customer"),
        ),
        migrations.AddIndex(
            model_name="auditreport",
            index=models.Index(fields=["customer", "-created_at"], name="audits_audi_custome_4aab38_idx"),
        ),
        migrations.RunPython(migrate_existing_visitors, migrations.RunPython.noop),
    ]
