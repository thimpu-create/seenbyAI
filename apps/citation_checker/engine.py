import json
from urllib.parse import urlparse

import httpx
from django.conf import settings


BRAVE_WEB_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_LLM_CONTEXT_URL = "https://api.search.brave.com/res/v1/llm/context"


async def run_citation_checks(crawl_data: dict, domain: str) -> list[dict]:
    queries = generate_queries_for_website(crawl_data, domain)
    results = []

    if settings.BRAVE_SEARCH_API_KEY:
        for query in queries[:3]:
            results.append(await check_brave_search(query, domain))
            results.append(await check_brave_llm_context(query, domain))

    if settings.LLM_API_BASE_URL:
        for query in queries[:2]:
            results.append(await check_llm_citation(query, domain, crawl_data))

    if not results:
        results.append(
            {
                "ai_engine": "citation_provider",
                "query_used": "Provider configuration",
                "status": "skipped",
                "was_cited": False,
                "citation_url": "",
                "ai_response_snippet": "No citation provider is configured. Add BRAVE_SEARCH_API_KEY or LLM_API_BASE_URL to enable MVP citation checks.",
                "all_citations": [],
            }
        )

    return results


async def check_brave_search(query: str, target_domain: str) -> dict:
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
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(BRAVE_WEB_SEARCH_URL, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return _failed(
            "brave_search",
            query,
            "Brave Search citation check could not run. Check BRAVE_SEARCH_API_KEY and provider access.",
            exc,
        )

    results = data.get("web", {}).get("results", [])
    citations = [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "description": item.get("description", ""),
        }
        for item in results
    ]
    cited = _find_matching_url(citations, target_domain)
    snippet = _make_snippet(citations)

    return {
        "ai_engine": "brave_search",
        "query_used": query,
        "status": "complete",
        "was_cited": bool(cited),
        "citation_url": cited or "",
        "ai_response_snippet": snippet,
        "all_citations": citations,
    }


async def check_brave_llm_context(query: str, target_domain: str) -> dict:
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": settings.BRAVE_SEARCH_API_KEY,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(BRAVE_LLM_CONTEXT_URL, headers=headers, params={"q": query})
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return _failed(
            "brave_llm_context",
            query,
            "Brave LLM context citation check could not run. Check BRAVE_SEARCH_API_KEY and provider access.",
            exc,
        )

    citations = []
    for bucket in data.get("grounding", {}).values():
        if not isinstance(bucket, list):
            continue
        for item in bucket:
            citations.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": " ".join(item.get("snippets", [])[:2])[:500],
                }
            )

    cited = _find_matching_url(citations, target_domain)
    return {
        "ai_engine": "brave_llm_context",
        "query_used": query,
        "status": "complete",
        "was_cited": bool(cited),
        "citation_url": cited or "",
        "ai_response_snippet": _make_snippet(citations),
        "all_citations": citations,
    }


async def check_llm_citation(query: str, target_domain: str, crawl_data: dict) -> dict:
    """
    Runs the citation-readiness simulation against any OpenAI-compatible
    chat completions endpoint -- Groq, Together AI, Fireworks, OpenRouter,
    a local Ollama instance (via its /v1/chat/completions endpoint), or any
    other provider implementing the same API shape.

    Configure via settings.LLM_API_BASE_URL, settings.LLM_API_KEY, and
    settings.LLM_MODEL. For local Ollama dev, point LLM_API_BASE_URL at
    something like http://localhost:11434/v1 (Ollama exposes an
    OpenAI-compatible endpoint at /v1/chat/completions) and leave
    LLM_API_KEY blank -- Ollama doesn't require one.
    """
    context = {
        "domain": target_domain,
        "page_titles": crawl_data.get("page_titles", [])[:6],
        "meta_descriptions": crawl_data.get("meta_descriptions", [])[:6],
        "signals": {
            "schema": crawl_data.get("has_faq_sections"),
            "authority_links": crawl_data.get("has_external_authority_links"),
            "author_bios": crawl_data.get("has_author_bios"),
            "fresh_dates": crawl_data.get("has_visible_dates"),
        },
    }
    system_prompt = "You are simulating an AI answer-engine citation readiness check."
    user_prompt = (
        "Use only the supplied website crawl context to judge whether this site is citation-ready "
        "for the query.\n\n"
        f"Query: {query}\nContext: {json.dumps(context)}\n\n"
        "First write your reasoning, then derive the verdict from that reasoning -- "
        "was_cited must agree with what you just wrote. If your reasoning says the site "
        "is NOT citation-ready, was_cited must be false.\n\n"
        "Respond with ONLY a JSON object, no other text, in exactly this shape, "
        "with reasoning written before was_cited:\n"
        '{"reasoning": "one or two sentence explanation", "was_cited": true or false}'
    )
    payload = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json"}
    if settings.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{settings.LLM_API_BASE_URL.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return _skipped(
            "llm_citation",
            query,
            "LLM citation simulation is configured but unavailable. Check LLM_API_BASE_URL, "
            "LLM_API_KEY, and LLM_MODEL, and confirm the provider is reachable.",
            exc,
        )

    try:
        raw_answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return _failed(
            "llm_citation",
            query,
            f"LLM citation check returned an unexpected response shape: {str(data)[:300]}",
        )

    try:
        parsed = json.loads(raw_answer)
        was_cited = bool(parsed.get("was_cited", False))
        reasoning = str(parsed.get("reasoning", "")).strip() or raw_answer[:500]
    except (json.JSONDecodeError, AttributeError):
        # Model didn't return valid JSON despite response_format=json_object --
        # fail safe rather than falling back to a substring match, which is what
        # caused the original bug (domain name appears in the explanation of why
        # it is NOT cited, producing a false positive).
        return _failed(
            "llm_citation",
            query,
            f"LLM citation check returned an unparseable response: {raw_answer[:300]}",
        )

    # Defense in depth: the prompt asks the model to write reasoning before the
    # verdict, but small/fast models can still set was_cited=true while writing
    # reasoning that says the opposite. If the reasoning clearly negates
    # citation-readiness, override the model's boolean rather than trust it blindly.
    negation_markers = ("not citation-ready", "not look citation-ready", "does not appear to be citation-ready", "isn't citation-ready", "is not citable")
    reasoning_lower = reasoning.lower()
    if was_cited and any(marker in reasoning_lower for marker in negation_markers):
        was_cited = False

    return {
        "ai_engine": "llm_citation",
        "query_used": query,
        "status": "complete",
        "was_cited": was_cited,
        "citation_url": f"https://{target_domain}" if was_cited else "",
        "ai_response_snippet": reasoning[:500],
        "all_citations": [{"title": target_domain, "url": f"https://{target_domain}"}] if was_cited else [],
    }


def generate_queries_for_website(crawl_data: dict, domain: str) -> list[str]:
    queries = []
    for title in crawl_data.get("page_titles", [])[:3]:
        cleaned = title.replace("|", " ").replace("-", " ").strip()
        if cleaned:
            queries.append(f"What is {cleaned}?")
            queries.append(f"Best information about {cleaned}")
    queries.append(f"About {domain}")
    queries.append(f"{domain} reviews")
    return list(dict.fromkeys(queries))[:5]


def _find_matching_url(citations, target_domain):
    normalized_target = _normalize_domain(target_domain)
    for citation in citations:
        url = citation.get("url", "")
        if normalized_target and normalized_target in _normalize_domain(urlparse(url).netloc):
            return url
    return ""


def _normalize_domain(value):
    return value.lower().replace("www.", "").strip()


def _make_snippet(citations):
    if not citations:
        return "No cited URLs were returned for this query."
    lines = []
    for item in citations[:3]:
        title = item.get("title") or item.get("url") or "Untitled result"
        url = item.get("url", "")
        lines.append(f"{title} - {url}")
    return "\n".join(lines)[:500]


def _failed(engine, query, message, exc=None):
    return {
        "ai_engine": engine,
        "query_used": query,
        "status": "failed",
        "was_cited": False,
        "citation_url": "",
        "ai_response_snippet": message,
        "all_citations": [],
        "provider_error": str(exc)[:500] if exc else "",
    }


def _skipped(engine, query, message, exc=None):
    return {
        "ai_engine": engine,
        "query_used": query,
        "status": "skipped",
        "was_cited": False,
        "citation_url": "",
        "ai_response_snippet": message,
        "all_citations": [],
        "provider_error": str(exc)[:500] if exc else "",
    }