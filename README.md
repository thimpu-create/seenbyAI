# SeenByAI

Docker-first MVP for auditing whether AI answer engines can discover, trust, and cite a website.

## What the MVP Does

- Email login/signup with Django allauth.
- Optional Google login/signup through allauth's Google provider.
- 2 free scans per account email address.
- Paid credits attach to the logged-in account email.
- Razorpay checkout for paid scan credits.
- Website crawl and 5-part AI citability scoring.
- Optional citation checks through Brave Search API and/or local Ollama.
- Web report plus downloadable PDF report.
- Docker Compose setup for local development and VPS deployment.

## Local Development

1. Copy the environment file:

```bash
cp .env.example .env
```

2. Add keys when you have them:

```ini
BRAVE_SEARCH_API_KEY=
OLLAMA_BASE_URL=http://host.docker.internal:11434
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=
```

3. Start the stack:

```bash
docker compose up --build
```

4. Open:

```text
http://localhost:8000
```

Routes:

- `/` public landing page
- `/dashboard/` logged-in scan dashboard
- `/accounts/login/` login
- `/accounts/signup/` signup

When testing through ngrok, the development env allows `*.ngrok-free.dev`. After changing `.env`, recreate the web container so Django receives the new host settings.

The `web` container runs migrations and static collection automatically on startup. The `celery` container processes audits in the background.

## Payment Settings

The MVP sells a configurable credit pack:

```ini
CREDIT_PACK_AMOUNT_PAISE=49900
CREDIT_PACK_CREDITS=10
FREE_AUDIT_LIMIT=2
```

Default price is INR 499 for 10 scan credits. Change this in `.env`.

Quota is enforced against the logged-in user's normalized lowercase email address. The browser cookie is still used as a convenience fallback for old development reports, but clearing cookies no longer resets the 2-scan free limit.

## Google Auth

Add credentials from Google Cloud Console:

```ini
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

For local development, add this authorized redirect URI in Google Cloud:

```text
http://localhost:8000/accounts/google/login/callback/
```

For production, add:

```text
https://yourdomain.com/accounts/google/login/callback/
```

If Google credentials are blank, email/password auth still works and the Google button shows a setup notice.

Razorpay flow:

- Server creates a Razorpay order.
- Browser opens Standard Checkout.
- Checkout returns `razorpay_payment_id`, `razorpay_order_id`, and `razorpay_signature`.
- Server verifies the signature before adding credits.
- Webhook endpoint is available at `/billing/razorpay/webhook/`.

## Citation Providers

For MVP, citation checks are provider-based:

- `BRAVE_SEARCH_API_KEY`: checks Brave Search and Brave LLM context citation sources.
- `OLLAMA_BASE_URL`: optional local model readiness simulation.

If neither provider is configured, audits still run and the report states that citation checks were skipped.

## VPS Deployment With Docker

On a VPS:

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

Recommended production values:

```ini
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
POSTGRES_PASSWORD=use-a-long-secret
DATABASE_URL=postgres://seenbyai:use-a-long-secret@db:5432/seenbyai
```

Put Nginx or Caddy in front of the web container for HTTPS, or use an AWS load balancer if deploying there.
