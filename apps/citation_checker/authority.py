from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from django.conf import settings

from .engine import BRAVE_WEB_SEARCH_URL


DIRECTORY_DOMAINS = {
    "linkedin.com/company",
    "crunchbase.com",
    "g2.com",
    "trustpilot.com",
    "capterra.com",
    "clutch.co",
    "yelp.com",
    "google.com/maps",
}
PRESS_DOMAINS = {
    "techcrunch.com",
    "forbes.com",
    "reuters.com",
    "businesswire.com",
    "prnewswire.com",
    "economictimes.indiatimes.com",
    "livemint.com",
    "yourstory.com",
    "inc42.com",
    "moneycontrol.com",
    "business-standard.com",
}


async def enrich_authority_signals(crawl_data: dict, domain: str) -> dict:
    data = dict(crawl_data)
    data.setdefault("authority_external_data", {})

    domain_age = await _fetch_domain_age_years(domain)
    if domain_age is not None:
        data["domain_age_years"] = domain_age
        data["authority_external_data"]["domain_age_checked"] = True
    else:
        data["authority_external_data"]["domain_age_checked"] = False

    if settings.BRAVE_SEARCH_API_KEY:
        brave_data = await _check_brave_authority(domain)
        data["authority_external_data"].update(brave_data)
        data["authority_external_checked"] = True
        data["has_wikipedia_mention"] = data.get("has_wikipedia_mention") or brave_data["wikipedia"]["found"]
        data["has_directory_listing"] = data.get("has_directory_listing") or brave_data["directory"]["found"]
        data["has_press_mentions"] = data.get("has_press_mentions") or brave_data["press"]["found"]
    else:
        data["authority_external_checked"] = False

    return data


async def _fetch_domain_age_years(domain: str):
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(f"https://rdap.org/domain/{domain}", headers={"Accept": "application/json"})
            response.raise_for_status()
            rdap = response.json()
    except Exception:
        return None

    registration_dates = []
    for event in rdap.get("events", []):
        action = str(event.get("eventAction", "")).lower()
        if action in {"registration", "registered", "domain registration"}:
            parsed = _parse_rdap_date(event.get("eventDate"))
            if parsed:
                registration_dates.append(parsed)

    if not registration_dates:
        return None

    oldest = min(registration_dates)
    return max((datetime.now(timezone.utc) - oldest).days // 365, 0)


async def _check_brave_authority(domain: str) -> dict:
    brand = _brand_from_domain(domain)
    checks = {
        "wikipedia": {
            "query": f'{brand} wikipedia wikidata',
            "domains": {"wikipedia.org", "wikidata.org"},
        },
        "directory": {
            "query": f'{brand} company profile reviews directory',
            "domains": DIRECTORY_DOMAINS,
        },
        "press": {
            "query": f'{brand} news funding press release',
            "domains": PRESS_DOMAINS,
        },
    }

    output = {}
    async with httpx.AsyncClient(timeout=20) as client:
        for key, config in checks.items():
            output[key] = await _run_brave_signal_check(client, config["query"], config["domains"])
    return output


async def _run_brave_signal_check(client, query: str, domains: set[str]) -> dict:
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": settings.BRAVE_SEARCH_API_KEY,
    }
    params = {
        "q": query,
        "count": 10,
        "search_lang": "en",
        "country": "us",
    }
    try:
        response = await client.get(BRAVE_WEB_SEARCH_URL, headers=headers, params=params)
        response.raise_for_status()
        results = response.json().get("web", {}).get("results", [])
    except Exception as exc:
        return {"found": False, "checked": False, "query": query, "error": str(exc)[:300], "matches": []}

    matches = []
    for item in results:
        url = item.get("url", "")
        normalized = _normalize_url(url)
        if any(marker in normalized for marker in domains):
            matches.append(
                {
                    "title": item.get("title", ""),
                    "url": url,
                    "description": item.get("description", ""),
                }
            )

    return {"found": bool(matches), "checked": True, "query": query, "matches": matches[:3]}


def _brand_from_domain(domain: str) -> str:
    host = domain.lower().replace("www.", "")
    return host.split(".")[0].replace("-", " ")


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.netloc.lower().replace('www.', '')}{parsed.path.lower()}"


def _parse_rdap_date(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
