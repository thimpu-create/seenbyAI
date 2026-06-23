"""
Tests for rate limiting on signup and login views.

Run with:
    docker compose -f docker-compose.prod.yml exec web python manage.py test apps.audits.tests.test_rate_limiting

Note: django-ratelimit uses Django's cache framework to track request counts.
These tests rely on the default LocMemCache (or whatever CACHES backend is
configured) being cleared between tests so counts don't leak across test cases.
"""

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(
    RATELIMIT_ENABLE=True,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class SignupRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.signup_url = reverse("account_signup")

    def _post_signup(self, email_suffix):
        return self.client.post(
            self.signup_url,
            {
                "email": f"ratelimit-test-{email_suffix}@example.com",
                "password1": "SuperSecret123!",
                "password2": "SuperSecret123!",
            },
        )

    def test_allows_requests_under_the_limit(self):
        """The first few signup attempts from the same IP should not be blocked."""
        for i in range(5):
            response = self._post_signup(i)
            self.assertNotEqual(
                response.status_code,
                429,
                f"Request {i + 1} was rate limited but should have been allowed.",
            )

    def test_blocks_requests_over_the_limit(self):
        """The 6th signup attempt within the window should be rate limited."""
        for i in range(5):
            self._post_signup(i)

        response = self._post_signup("sixth")
        self.assertEqual(response.status_code, 429)

    def test_rate_limit_is_scoped_per_ip(self):
        """A different client IP should not be blocked by another IP's attempts."""
        for i in range(5):
            self._post_signup(i)
        blocked_response = self._post_signup("sixth")
        self.assertEqual(blocked_response.status_code, 429)

        other_client_response = self.client.post(
            self.signup_url,
            {
                "email": "ratelimit-test-other-ip@example.com",
                "password1": "SuperSecret123!",
                "password2": "SuperSecret123!",
            },
            REMOTE_ADDR="10.0.0.99",
        )
        self.assertNotEqual(other_client_response.status_code, 429)


@override_settings(
    RATELIMIT_ENABLE=True,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class LoginRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.login_url = reverse("account_login")

    def _post_login(self, password="wrong-password"):
        return self.client.post(
            self.login_url,
            {
                "login": "nonexistent-user@example.com",
                "password": password,
            },
        )

    def test_allows_requests_under_the_limit(self):
        """The first several failed login attempts should not be blocked yet."""
        for i in range(10):
            response = self._post_login()
            self.assertNotEqual(
                response.status_code,
                429,
                f"Login attempt {i + 1} was rate limited but should have been allowed.",
            )

    def test_blocks_requests_over_the_limit(self):
        """The 11th login attempt within the window should be rate limited."""
        for i in range(10):
            self._post_login()

        response = self._post_login()
        self.assertEqual(response.status_code, 429)

    def test_returns_custom_429_page(self):
        """The rate-limited response should render the custom 429 template, not a bare error."""
        for i in range(10):
            self._post_login()

        response = self._post_login()
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Too many attempts", status_code=429)