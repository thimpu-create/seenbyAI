# Generated for the SeenByAI MVP.
import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("audits", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Purchase",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("email", models.EmailField(max_length=254)),
                ("amount_paise", models.PositiveIntegerField()),
                ("currency", models.CharField(default="INR", max_length=10)),
                ("credits", models.PositiveIntegerField()),
                ("status", models.CharField(choices=[("created", "Created"), ("paid", "Paid"), ("failed", "Failed")], default="created", max_length=20)),
                ("razorpay_order_id", models.CharField(blank=True, db_index=True, max_length=100)),
                ("razorpay_payment_id", models.CharField(blank=True, max_length=100)),
                ("razorpay_signature", models.CharField(blank=True, max_length=255)),
                ("raw_response", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("visitor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="purchases", to="audits.visitor")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
