from allauth.account.views import SignupView, LoginView
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit


@method_decorator(ratelimit(key="ip", rate="5/h", block=True), name="post")
class RateLimitedSignupView(SignupView):
    pass


@method_decorator(ratelimit(key="ip", rate="10/h", block=True), name="post")
class RateLimitedLoginView(LoginView):
    pass


def ratelimited_view(request, exception):
    return render(request, "429.html", status=429)