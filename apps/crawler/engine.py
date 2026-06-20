import asyncio
import re
import time
from datetime import datetime, timezone
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from django.conf import settings


TIMEOUT = 12
SOCIAL_DOMAINS = [
    "twitter.com",
    "x.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
]
AUTHORITY_DOMAINS = [
    ".gov",
    ".edu",
    "wikipedia.org",
    "pubmed.ncbi.nlm.nih.gov",
    "reuters.com",
    "bbc.com",
    "nature.com",
    "who.int",
    "oecd.org",
]


async def crawl_website(url: str) -> dict:
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    data = _empty_crawl_data(parsed.scheme == "https")

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=TIMEOUT,
        headers={"User-Agent": "SeenByAI Audit Bot/1.0"},
    ) as client:
        try:
            start = time.monotonic()
            response = await client.get(url)
            data["response_time_ms"] = int((time.monotonic() - start) * 1000)
            data["homepage_status_code"] = response.status_code
            response.raise_for_status()
        except Exception as exc:
            data["error_message"] = str(exc)
            return data

        soup = BeautifulSoup(response.text, "lxml")
        _parse_page(soup, url, base_url, data, is_homepage=True)

        await _check_support_files(client, base_url, data)

        links = _extract_internal_links(soup, base_url)
        visited = {url}
        word_counts = []
        error_count = 0

        semaphore = asyncio.Semaphore(6)

        async def fetch_and_parse(link):
            nonlocal error_count
            async with semaphore:
                try:
                    page_response = await client.get(link)
                    if page_response.status_code >= 400:
                        error_count += 1
                        return
                    page_soup = BeautifulSoup(page_response.text, "lxml")
                    _parse_page(page_soup, link, base_url, data)
                    word_counts.append(_word_count(page_soup))
                except Exception:
                    error_count += 1

        selected_links = []
        for link in links:
            if link in visited:
                continue
            visited.add(link)
            selected_links.append(link)
            if len(selected_links) >= settings.CRAWL_MAX_PAGES:
                break

        await asyncio.gather(*(fetch_and_parse(link) for link in selected_links))

        homepage_words = _word_count(soup)
        if homepage_words:
            word_counts.append(homepage_words)

        data["pages_crawled"] = len(visited)
        data["avg_word_count"] = int(sum(word_counts) / len(word_counts)) if word_counts else 0
        data["error_rate"] = error_count / max(len(visited), 1)

    return data


async def fetch_html(url: str) -> str:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=TIMEOUT) as client:
            response = await client.get(url, headers={"User-Agent": "SeenByAI Audit Bot/1.0"})
            response.raise_for_status()
            return response.text
    except Exception:
        return ""


def _empty_crawl_data(uses_https):
    return {
        "uses_https": uses_https,
        "response_time_ms": None,
        "homepage_status_code": None,
        "has_viewport_meta": False,
        "robots_txt_reachable": False,
        "sitemap_reachable": False,
        "has_canonical": False,
        "error_rate": 0.0,
        "has_about_page": False,
        "has_author_bios": False,
        "has_contact_page": False,
        "has_privacy_policy": False,
        "has_terms": False,
        "has_external_authority_links": False,
        "has_visible_dates": False,
        "has_social_links": False,
        "avg_word_count": 0,
        "has_faq_sections": False,
        "has_proper_headings": False,
        "days_since_last_update": 999,
        "has_direct_answer_format": False,
        "pages_crawled": 0,
        "domain_age_years": 0,
        "has_social_presence": False,
        "has_wikipedia_mention": False,
        "has_directory_listing": False,
        "has_press_mentions": False,
        "page_titles": [],
        "meta_descriptions": [],
        "important_pages": [],
    }


async def _check_support_files(client, base_url, data):
    try:
        robots = await client.get(f"{base_url}/robots.txt")
        data["robots_txt_reachable"] = robots.status_code == 200
    except Exception:
        pass

    for sitemap_path in ("/sitemap.xml", "/sitemap_index.xml"):
        try:
            sitemap = await client.get(f"{base_url}{sitemap_path}")
            if sitemap.status_code == 200:
                data["sitemap_reachable"] = True
                return
        except Exception:
            pass


def _parse_page(soup, url, base_url, data, is_homepage=False):
    url_lower = url.lower()
    text = " ".join(soup.get_text(" ").split()).lower()

    title = soup.find("title")
    if title and title.get_text(strip=True):
        _append_unique(data["page_titles"], title.get_text(strip=True), 12)

    meta_description = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    if meta_description and meta_description.get("content"):
        _append_unique(data["meta_descriptions"], meta_description["content"].strip(), 12)

    if is_homepage:
        data["has_viewport_meta"] = bool(soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)}))
        data["has_canonical"] = bool(soup.find("link", rel=re.compile("canonical", re.I)))

    _detect_trust_pages(url_lower, text, data)
    _detect_content_patterns(soup, text, data)
    _detect_links(soup, base_url, data)
    _detect_authority_mentions(text, data)


def _detect_trust_pages(url_lower, text, data):
    page_patterns = [
        ("has_about_page", ["/about", "/about-us", "/who-we-are"], ["about us", "our story"]),
        ("has_contact_page", ["/contact", "/contact-us", "/get-in-touch"], ["contact us", "get in touch"]),
        ("has_privacy_policy", ["/privacy", "/privacy-policy"], ["privacy policy"]),
        ("has_terms", ["/terms", "/terms-of-service", "/tos"], ["terms of service", "terms and conditions"]),
    ]
    for field, url_markers, text_markers in page_patterns:
        if any(marker in url_lower for marker in url_markers) or any(marker in text for marker in text_markers):
            data[field] = True


def _detect_content_patterns(soup, text, data):
    if any(marker in text for marker in ["about the author", "written by", "author bio", "reviewed by"]):
        data["has_author_bios"] = True

    if any(marker in text for marker in ["frequently asked questions", "faq", "common questions", "people also ask"]):
        data["has_faq_sections"] = True

    h1s = soup.find_all("h1")
    h2s = soup.find_all("h2")
    if len(h1s) == 1 and len(h2s) >= 2:
        data["has_proper_headings"] = True

    date_value = _extract_visible_date(soup, text)
    if date_value is not None:
        data["has_visible_dates"] = True
        data["days_since_last_update"] = min(data["days_since_last_update"], date_value)

    first_p = soup.find("p")
    if first_p:
        words = first_p.get_text(" ").split()
        if 20 <= len(words) <= 90:
            data["has_direct_answer_format"] = True


def _detect_links(soup, base_url, data):
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip().lower()
        if any(domain in href for domain in SOCIAL_DOMAINS):
            data["has_social_links"] = True
            data["has_social_presence"] = True
        if href.startswith("http") and base_url not in href and any(domain in href for domain in AUTHORITY_DOMAINS):
            data["has_external_authority_links"] = True


def _detect_authority_mentions(text, data):
    if "wikipedia" in text or "wikidata" in text:
        data["has_wikipedia_mention"] = True
    if any(marker in text for marker in ["google business profile", "yelp", "trustpilot", "clutch.co", "g2.com"]):
        data["has_directory_listing"] = True
    if any(marker in text for marker in ["press release", "as seen in", "featured in", "media coverage", "newsroom"]):
        data["has_press_mentions"] = True


def _extract_internal_links(soup, base_url):
    links = []
    base_host = urlparse(base_url).netloc
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urldefrag(urljoin(base_url, href))[0].rstrip("/")
        parsed = urlparse(absolute)
        if parsed.netloc == base_host and absolute not in links:
            links.append(absolute)
    return links


def _extract_visible_date(soup, text):
    time_tag = soup.find("time")
    candidates = []
    if time_tag:
        candidates.extend([time_tag.get("datetime", ""), time_tag.get_text(" ", strip=True)])
    candidates.extend(re.findall(r"\b(?:20\d{2}|19\d{2})[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01])\b", text))

    for value in candidates:
        parsed = _parse_date(value)
        if parsed:
            return max((datetime.now(timezone.utc) - parsed).days, 0)

    if any(marker in text for marker in ["published", "updated", "last modified"]):
        return 90
    return None


def _parse_date(value):
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00").replace("/", "-").replace(".", "-")
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(normalized[:24], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _word_count(soup):
    return len(re.findall(r"\b\w+\b", soup.get_text(" ")))


def _append_unique(items, value, limit):
    if value and value not in items and len(items) < limit:
        items.append(value)
