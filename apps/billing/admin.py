from django.contrib import admin

from .models import Purchase


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("email", "customer", "status", "amount_paise", "credits", "razorpay_order_id", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("email", "customer__email", "razorpay_order_id", "razorpay_payment_id")
