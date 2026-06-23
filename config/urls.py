from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from apps.audits.auth_views import RateLimitedLoginView, RateLimitedSignupView


def health(request):
    return JsonResponse({"ok": True})


urlpatterns = [
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("accounts/signup/", RateLimitedSignupView.as_view(), name="account_signup"),
    path("accounts/login/", RateLimitedLoginView.as_view(), name="account_login"),
    path("accounts/", include("allauth.urls")),
    path("billing/", include("apps.billing.urls")),
    path("", include("apps.audits.urls")),
]