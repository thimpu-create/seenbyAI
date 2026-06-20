import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import CheckoutForm
from .models import Purchase
from .razorpay_client import create_order, is_configured, verify_checkout_signature, verify_webhook_signature
from apps.audits.models import Customer


@login_required
def checkout(request):
    visitor = request.visitor
    customer, _ = Customer.objects.get_or_create(email=Customer.normalize_email(request.user.email))
    if visitor.email != customer.email:
        visitor.email = customer.email
        visitor.save(update_fields=["email", "last_seen_at"])

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            if not is_configured():
                messages.error(request, "Razorpay is not configured yet. Add keys to .env and restart Docker.")
                return redirect("checkout")

            purchase = Purchase.objects.create(
                visitor=visitor,
                customer=customer,
                email=customer.email,
                amount_paise=settings.CREDIT_PACK_AMOUNT_PAISE,
                currency=settings.RAZORPAY_CURRENCY,
                credits=settings.CREDIT_PACK_CREDITS,
            )
            try:
                order = create_order(purchase)
            except Exception as exc:
                purchase.status = Purchase.STATUS_FAILED
                purchase.raw_response = {"error": str(exc)}
                purchase.save(update_fields=["status", "raw_response"])
                messages.error(request, "Razorpay order creation failed. Check your keys and try again.")
                return redirect("checkout")
            purchase.razorpay_order_id = order["id"]
            purchase.raw_response = order
            purchase.save(update_fields=["razorpay_order_id", "raw_response"])
            return render(request, "billing/pay.html", _payment_context(request, purchase))
    else:
        form = CheckoutForm()

    return render(
        request,
        "billing/checkout.html",
        {
            "form": form,
            "razorpay_configured": is_configured(),
            "amount_rupees": settings.CREDIT_PACK_AMOUNT_PAISE / 100,
            "credits": settings.CREDIT_PACK_CREDITS,
            "customer": customer,
        },
    )


@require_POST
@login_required
def verify_payment(request):
    purchase = get_object_or_404(Purchase, id=request.POST.get("purchase_id"), customer__email=Customer.normalize_email(request.user.email))
    payment_id = request.POST.get("razorpay_payment_id", "")
    order_id = request.POST.get("razorpay_order_id", "")
    signature = request.POST.get("razorpay_signature", "")

    if not payment_id or not order_id or not signature:
        return JsonResponse({"ok": False, "error": "Missing payment verification fields."}, status=400)
    if order_id != purchase.razorpay_order_id:
        return JsonResponse({"ok": False, "error": "Order mismatch."}, status=400)

    try:
        verify_checkout_signature(order_id, payment_id, signature)
    except Exception:
        purchase.status = Purchase.STATUS_FAILED
        purchase.raw_response = {"error": "signature_verification_failed"}
        purchase.save(update_fields=["status", "raw_response"])
        return JsonResponse({"ok": False, "error": "Payment signature verification failed."}, status=400)

    _fulfill_purchase(purchase, payment_id, signature, dict(request.POST.items()))
    return JsonResponse({"ok": True, "redirect_url": reverse("payment_success", args=[purchase.id])})


@login_required
def payment_success(request, purchase_id):
    purchase = get_object_or_404(Purchase, id=purchase_id, customer__email=Customer.normalize_email(request.user.email))
    return render(request, "billing/success.html", {"purchase": purchase})


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not verify_webhook_signature(request.body, signature):
        return HttpResponseBadRequest("Invalid signature")

    payload = json.loads(request.body.decode("utf-8"))
    event = payload.get("event", "")
    payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
    order_id = payment.get("order_id", "")
    payment_id = payment.get("id", "")

    if event in {"payment.captured", "order.paid"} and order_id:
        purchase = Purchase.objects.filter(razorpay_order_id=order_id).first()
        if purchase:
            _fulfill_purchase(purchase, payment_id, "", payload)
    return JsonResponse({"ok": True})


def _fulfill_purchase(purchase, payment_id, signature, raw_response):
    with transaction.atomic():
        purchase = Purchase.objects.select_for_update().select_related("visitor").get(pk=purchase.pk)
        marked = purchase.mark_paid(payment_id=payment_id, signature=signature, raw_response=raw_response)
        if marked:
            customer = purchase.customer
            if customer is None:
                customer, _ = Customer.objects.select_for_update().get_or_create(email=Customer.normalize_email(purchase.email))
                purchase.customer = customer
                purchase.save(update_fields=["customer"])
            customer.paid_audit_credits += purchase.credits
            customer.save(update_fields=["paid_audit_credits", "updated_at"])

            visitor = purchase.visitor
            visitor.email = customer.email
            visitor.save(update_fields=["email", "last_seen_at"])


def _payment_context(request, purchase):
    return {
        "purchase": purchase,
        "key_id": settings.RAZORPAY_KEY_ID,
        "callback_url": request.build_absolute_uri(reverse("verify_payment")),
        "success_url": reverse("payment_success", args=[purchase.id]),
        "amount_rupees": purchase.amount_paise / 100,
        "credits": purchase.credits,
    }
