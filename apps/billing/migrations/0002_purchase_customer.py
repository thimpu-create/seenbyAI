from django.db import migrations, models
import django.db.models.deletion


def migrate_existing_purchases(apps, schema_editor):
    Customer = apps.get_model("audits", "Customer")
    Purchase = apps.get_model("billing", "Purchase")

    for purchase in Purchase.objects.exclude(email=""):
        email = purchase.email.strip().lower()
        if not email:
            continue
        customer, _ = Customer.objects.get_or_create(email=email)
        Purchase.objects.filter(pk=purchase.pk).update(customer=customer, email=email)


class Migration(migrations.Migration):
    dependencies = [
        ("audits", "0002_customer_email_quota"),
        ("billing", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchase",
            name="customer",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="purchases", to="audits.customer"),
        ),
        migrations.RunPython(migrate_existing_purchases, migrations.RunPython.noop),
    ]
