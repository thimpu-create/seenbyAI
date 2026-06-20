import hashlib
import uuid

from django.core import signing
from django.utils.deprecation import MiddlewareMixin

from .models import Visitor


VISITOR_COOKIE_NAME = "seenbyai_vid"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365


class VisitorMiddleware(MiddlewareMixin):
    def process_request(self, request):
        raw_cookie = request.COOKIES.get(VISITOR_COOKIE_NAME)
        token = self._unsign_token(raw_cookie)
        created = False

        if token is None:
            token = uuid.uuid4()
            created = True

        ip_hash = self._hash_value(self._get_ip(request))
        ua_hash = self._hash_value(request.META.get("HTTP_USER_AGENT", ""))

        visitor, _ = Visitor.objects.get_or_create(
            cookie_token=token,
            defaults={"ip_hash": ip_hash, "user_agent_hash": ua_hash},
        )

        updates = []
        if visitor.ip_hash != ip_hash:
            visitor.ip_hash = ip_hash
            updates.append("ip_hash")
        if visitor.user_agent_hash != ua_hash:
            visitor.user_agent_hash = ua_hash
            updates.append("user_agent_hash")
        if updates:
            updates.append("last_seen_at")
            visitor.save(update_fields=updates)

        request.visitor = visitor
        request._set_visitor_cookie = created or raw_cookie is None

    def process_response(self, request, response):
        visitor = getattr(request, "visitor", None)
        if visitor and getattr(request, "_set_visitor_cookie", False):
            response.set_cookie(
                VISITOR_COOKIE_NAME,
                signing.Signer().sign(str(visitor.cookie_token)),
                max_age=COOKIE_MAX_AGE,
                httponly=True,
                samesite="Lax",
                secure=request.is_secure(),
            )
        return response

    def _unsign_token(self, raw_cookie):
        if not raw_cookie:
            return None
        try:
            return uuid.UUID(signing.Signer().unsign(raw_cookie))
        except (signing.BadSignature, ValueError, TypeError):
            return None

    def _get_ip(self, request):
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")

    def _hash_value(self, value):
        return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""
