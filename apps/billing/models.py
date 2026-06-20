import uuid

from django.db import models
from django.utils import timezone

from apps.audits.models import Customer, Visitor


class Purchase(models.Model):
    STATUS_CREATED = "created"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_CREATED, "Created"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name="purchases")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="purchases", null=True, blank=True)
    email = models.EmailField()
    amount_paise = models.PositiveIntegerField()
    currency = models.CharField(max_length=10, default="INR")
    credits = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CREATED)

    razorpay_order_id = models.CharField(max_length=100, blank=True, db_index=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    razorpay_signature = models.CharField(max_length=255, blank=True)
    raw_response = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} - {self.status}"

    def mark_paid(self, payment_id="", signature="", raw_response=None):
        if self.status == self.STATUS_PAID:
            return False
        self.status = self.STATUS_PAID
        self.razorpay_payment_id = payment_id or self.razorpay_payment_id
        self.razorpay_signature = signature or self.razorpay_signature
        self.raw_response = raw_response or self.raw_response
        self.paid_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "razorpay_payment_id",
                "razorpay_signature",
                "raw_response",
                "paid_at",
            ]
        )
        return True
