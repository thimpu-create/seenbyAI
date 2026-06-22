import json
import re
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
    readiness_profile = _build_readiness_profile(crawl_data)
    context = {
        "domain": target_domain,
        "page_titles": crawl_data.get("page_titles", [])[:6],
        "meta_descriptions": crawl_data.get("meta_descriptions", [])[:6],
        "important_pages": crawl_data.get("important_pages", [])[:8],
        "schema_types_detected": crawl_data.get("schema_types_detected", []),
        "readiness_score": readiness_profile["score"],
        "present_signals": readiness_profile["present"],
        "missing_evidence": readiness_profile["missing"],
        "recommended_actions": readiness_profile["next_steps"],
        "signals": {
            "answer_schema_or_faq": readiness_profile["has_answer_schema_or_faq"],
            "authority_links": crawl_data.get("has_external_authority_links"),
            "author_bios": crawl_data.get("has_author_bios"),
            "fresh_dates": crawl_data.get("has_visible_dates"),
            "content_depth": crawl_data.get("avg_word_count", 0),
            "pages_crawled": crawl_data.get("pages_crawled", 0),
        },
    }
    system_prompt = (
        "You are simulating an AI answer-engine citation readiness check. "
        "You are not verifying a live citation. Be specific, practical, and honest."
    )
    user_prompt = (
        "Use only the supplied website crawl context to judge whether this site is citation-ready "
        "for the query.\n\n"
        f"Query: {query}\nContext: {json.dumps(context)}\n\n"
        "Return a product-ready diagnosis, not a generic paragraph. Keep it short, but include the "
        "specific evidence the crawl found and the specific evidence still missing. "
        "is_likely_citation_ready must be false when the readiness_score is below 65.\n\n"
        "Respond with ONLY a JSON object, no other text, in exactly this shape:\n"
        "{"
        '"answer_preview": "one sentence describing what an AI can understand from the crawled site today", '
        '"reasoning": "one sentence explaining the verdict", '
        '"missing_evidence": ["specific missing signal", "specific missing signal"], '
        '"next_steps": ["specific action", "specific action"], '
        '"confidence": "low, medium, or high", '
        '"is_likely_citation_ready": true or false'
        "}"
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
    except (json.JSONDecodeError, AttributeError):
        parsed = _fallback_readiness_payload(target_domain, readiness_profile)

    is_likely_ready = bool(parsed.get("is_likely_citation_ready", parsed.get("was_cited", False)))
    if readiness_profile["score"] < 65:
        is_likely_ready = False

    answer_preview = str(parsed.get("answer_preview", "")).strip() or _answer_preview(target_domain, readiness_profile)
    reasoning = str(parsed.get("reasoning", "")).strip() or _readiness_reasoning(is_likely_ready, readiness_profile)
    missing_evidence = _clean_list(parsed.get("missing_evidence"), readiness_profile["missing"])
    next_steps = _clean_list(parsed.get("next_steps"), readiness_profile["next_steps"])
    confidence = str(parsed.get("confidence", "medium")).strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "medium"

    # Defense in depth: the prompt asks the model to write reasoning before the
    # verdict, but small/fast models can still set the boolean true while writing
    # reasoning that says the opposite. If the reasoning clearly negates
    # citation-readiness, override the model's boolean rather than trust it blindly.
    negation_markers = ("not citation-ready", "not look citation-ready", "does not appear to be citation-ready", "isn't citation-ready", "is not citable")
    reasoning_lower = reasoning.lower()
    if is_likely_ready and any(marker in reasoning_lower for marker in negation_markers):
        is_likely_ready = False

    snippet = _format_readiness_snippet(
        is_likely_ready=is_likely_ready,
        profile=readiness_profile,
        answer_preview=answer_preview,
        reasoning=reasoning,
        missing_evidence=missing_evidence,
        next_steps=next_steps,
        confidence=confidence,
    )

    return {
        "ai_engine": "llm_citation",
        "query_used": query,
        "status": "complete",
        # This field is reused as the simulation verdict. It is intentionally
        # excluded from live citation counts in report context.
        "was_cited": is_likely_ready,
        "citation_url": "",
        "ai_response_snippet": snippet[:1400],
        "all_citations": [
            {
                "type": "readiness_profile",
                "score": readiness_profile["score"],
                "missing_evidence": missing_evidence,
                "next_steps": next_steps,
            }
        ],
    }


def generate_queries_for_website(crawl_data: dict, domain: str) -> list[str]:
    queries = []
    entity_name = _entity_name_from_titles(crawl_data.get("page_titles", []), domain)
    if entity_name:
        queries.append(f"Who is {entity_name}?")
        queries.append(f"What does {entity_name} do?")
    queries.append(f"About {domain}")
    queries.append(f"{domain} reviews")
    return list(dict.fromkeys(queries))[:5]


def build_readiness_display_snippet(
    crawl_data: dict,
    target_domain: str,
    *,
    raw_reasoning: str = "",
    is_likely_ready: bool = False,
) -> str:
    if raw_reasoning.strip().startswith("Verdict:"):
        return raw_reasoning.strip()

    profile = _build_readiness_profile(crawl_data or {})
    if profile["score"] < 65:
        is_likely_ready = False
    reasoning = _readiness_reasoning(is_likely_ready, profile)

    return _format_readiness_snippet(
        is_likely_ready=is_likely_ready,
        profile=profile,
        answer_preview=_answer_preview(target_domain, profile),
        reasoning=reasoning,
        missing_evidence=profile["missing"],
        next_steps=profile["next_steps"],
        confidence="medium",
    )


def _build_readiness_profile(crawl_data: dict) -> dict:
    schema_types = set(crawl_data.get("schema_types_detected", []))
    has_entity_schema = bool(schema_types.intersection({"Organization", "Person", "LocalBusiness", "WebSite"}))
    has_answer_schema = bool(schema_types.intersection({"FAQPage", "Article", "BlogPosting", "HowTo"}))
    has_answer_schema_or_faq = has_answer_schema or crawl_data.get("has_faq_sections")

    checks = [
        (
            has_entity_schema,
            18,
            "Entity schema is present",
            "Entity schema such as Organization, Person, or WebSite",
            "Add Organization or Person JSON-LD with name, URL, logo/photo, sameAs profiles, and contact details.",
        ),
        (
            has_answer_schema_or_faq,
            16,
            "Answer-ready schema or FAQ content is present",
            "FAQPage, Article, BlogPosting, HowTo, or clear FAQ content",
            "Add FAQPage or Article/BlogPosting schema to pages that answer common questions.",
        ),
        (
            crawl_data.get("has_author_bios") or crawl_data.get("has_about_page"),
            12,
            "Human or brand identity is explained",
            "Author, owner, or brand bio with credentials",
            "Add a short bio with role, experience, credentials, and links to verified profiles.",
        ),
        (
            crawl_data.get("has_external_authority_links"),
            12,
            "External authority links are present",
            "Links to credible third-party sources or references",
            "Cite credible sources, standards, publications, or official profiles where claims are made.",
        ),
        (
            crawl_data.get("has_visible_dates"),
            10,
            "Freshness dates are visible",
            "Visible published or last-updated dates",
            "Show published and last-updated dates on important pages.",
        ),
        (
            crawl_data.get("has_direct_answer_format") and crawl_data.get("has_proper_headings"),
            12,
            "Answer-friendly page structure is present",
            "Direct answers with clear H1/H2 structure",
            "Start key pages with a direct answer, then organize details under question-style H2s.",
        ),
        (
            crawl_data.get("avg_word_count", 0) >= 800 or crawl_data.get("pages_crawled", 0) >= 5,
            10,
            "Enough crawlable content was found",
            "Enough crawlable depth for the topic",
            "Expand thin pages with services, proof, case studies, FAQs, and examples.",
        ),
        (
            crawl_data.get("has_social_links") or crawl_data.get("has_directory_listing") or crawl_data.get("has_press_mentions"),
            10,
            "Third-party identity signals are present",
            "Verified social, directory, or press signals",
            "Link official LinkedIn, GitHub, Crunchbase, Google Business Profile, press, or directory profiles.",
        ),
    ]

    score = 0
    present = []
    missing = []
    next_steps = []
    for passed, points, present_label, missing_label, next_step in checks:
        if passed:
            score += points
            present.append(present_label)
        else:
            missing.append(missing_label)
            next_steps.append(next_step)

    return {
        "score": score,
        "present": present[:5],
        "missing": missing[:5],
        "next_steps": next_steps[:5],
        "has_answer_schema_or_faq": bool(has_answer_schema_or_faq),
        "title": (crawl_data.get("page_titles") or [""])[0],
        "description": (crawl_data.get("meta_descriptions") or [""])[0],
    }


def _fallback_readiness_payload(target_domain: str, profile: dict) -> dict:
    return {
        "answer_preview": _answer_preview(target_domain, profile),
        "reasoning": _readiness_reasoning(profile["score"] >= 65, profile),
        "missing_evidence": profile["missing"],
        "next_steps": profile["next_steps"],
        "confidence": "medium",
        "is_likely_citation_ready": profile["score"] >= 65,
    }


def _answer_preview(target_domain: str, profile: dict) -> str:
    title = profile.get("title") or target_domain
    description = profile.get("description")
    if description:
        return f"An answer engine can identify {title} from the page title and meta description, but needs stronger proof signals before citing it confidently."
    return f"An answer engine can identify {title}, but the crawl found limited supporting context for confident citation."


def _readiness_reasoning(is_likely_ready: bool, profile: dict) -> str:
    if is_likely_ready:
        return "The crawl found enough entity, structure, and trust signals for a basic citation-readiness pass."
    if profile["missing"]:
        return f"The crawl found useful identity information, but citation confidence is held back by missing: {_join_sentence_items(profile['missing'][:3])}"
    return "The crawl did not find enough structured, trustworthy evidence for a confident citation-readiness pass."


def _format_readiness_snippet(
    *,
    is_likely_ready: bool,
    profile: dict,
    answer_preview: str,
    reasoning: str,
    missing_evidence: list[str],
    next_steps: list[str],
    confidence: str,
) -> str:
    verdict = "Likely ready for answer inclusion, but still needs live citation proof." if is_likely_ready else "Needs stronger evidence before answer engines are likely to cite it."
    lines = [
        f"Verdict: {verdict}",
        f"Readiness score: {profile['score']}/100",
        f"What AI can understand now: {answer_preview}",
        f"Why: {reasoning}",
    ]
    if missing_evidence:
        lines.append(f"Missing evidence: {_join_sentence_items(missing_evidence[:4])}")
    if next_steps:
        lines.append(f"Next steps: {_join_sentence_items(next_steps[:3])}")
    lines.append(f"Confidence: {confidence.title()}")
    return "\n".join(lines)


def _clean_list(value, fallback):
    if isinstance(value, list):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if cleaned:
            return cleaned[:5]
    return fallback[:5]


def _join_sentence_items(items: list[str]) -> str:
    cleaned = [str(item).strip().rstrip(".") for item in items if str(item).strip()]
    return f"{'; '.join(cleaned)}."


def _entity_name_from_titles(titles: list[str], domain: str) -> str:
    for title in titles[:3]:
        normalized = title.replace("\u2014", "|").replace("\u2013", "|")
        normalized = re.sub(r"\s[-|:]\s", "|", normalized)
        entity = normalized.split("|")[0].strip()
        entity = re.sub(r"\s+", " ", entity)
        if entity and entity.lower() not in {"home", "homepage", "welcome"}:
            return entity[:80]
    return domain


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
