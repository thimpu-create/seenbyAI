from django.conf import settings

from .models import Customer


def product_context(request):
    visitor = getattr(request, "visitor", None)
    active_customer = None
    if request.user.is_authenticated and request.user.email:
        print("Authenticated user email:", request.user.email)
        active_customer = Customer.objects.filter(email=Customer.normalize_email(request.user.email)).first()
    elif visitor and visitor.email:
        print("Visitor email:", visitor.email)
        active_customer = Customer.objects.filter(email=Customer.normalize_email(visitor.email)).first()
    return {
        "product_name": settings.PRODUCT_NAME,
        "product_tagline": settings.PRODUCT_TAGLINE,
        "free_audit_limit": settings.FREE_AUDIT_LIMIT,
        "support_email": settings.SUPPORT_EMAIL,
        "scan_pack_price_rupees": settings.CREDIT_PACK_AMOUNT_PAISE // 100,
        "scan_pack_size": settings.CREDIT_PACK_CREDITS,
        "visitor": visitor,
        "active_customer": active_customer,
        "quota_scans_remaining": active_customer.total_audits_remaining if active_customer else settings.FREE_AUDIT_LIMIT,
        "google_oauth_configured": bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET),
    }