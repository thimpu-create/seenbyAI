import hmac
import hashlib

import razorpay
from django.conf import settings


def is_configured():
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def get_client():
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_order(purchase):
    client = get_client()
    return client.order.create(
        {
            "amount": purchase.amount_paise,
            "currency": purchase.currency,
            "receipt": str(purchase.id)[:40],
            "notes": {
                "purchase_id": str(purchase.id),
                "visitor_id": str(purchase.visitor_id),
                "credits": str(purchase.credits),
            },
        }
    )


def verify_checkout_signature(order_id, payment_id, signature):
    client = get_client()
    client.utility.verify_payment_signature(
        {
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        }
    )


def verify_webhook_signature(payload: bytes, signature: str):
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        return False
    digest = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(digest, signature or "")
