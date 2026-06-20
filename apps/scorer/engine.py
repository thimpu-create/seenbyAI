SCORING_WEIGHTS = {
    "technical": 0.15,
    "schema": 0.20,
    "eeat": 0.25,
    "content": 0.25,
    "authority": 0.15,
}


def score_technical(crawl_data: dict) -> dict:
    findings = []
    score = 0.0

    if crawl_data.get("uses_https"):
        score += 20
        findings.append(_pass("Uses HTTPS", "The site is served over HTTPS.", 20))
    else:
        findings.append(_fail("critical", "Not using HTTPS", "The site is not served over HTTPS.", "Install SSL and redirect all HTTP traffic to HTTPS.", -20))

    response_ms = crawl_data.get("response_time_ms") or 9999
    if response_ms < 3000:
        score += 15
        findings.append(_pass("Fast response time", f"Homepage responded in {response_ms} ms.", 15))
    else:
        findings.append(_fail("medium", "Slow page response", f"Homepage took {response_ms} ms to respond.", "Optimize server response time, use caching, and consider a CDN.", -10))

    if crawl_data.get("has_viewport_meta"):
        score += 15
        findings.append(_pass("Mobile viewport present", "Viewport metadata is present.", 15))
    else:
        findings.append(_fail("high", "Missing viewport meta tag", "No mobile viewport tag was found.", "Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> to the head.", -15))

    if crawl_data.get("robots_txt_reachable"):
        score += 10
        findings.append(_pass("robots.txt reachable", "robots.txt is accessible.", 10))
    else:
        findings.append(_fail("low", "Missing robots.txt", "robots.txt was not reachable.", "Add /robots.txt and explicitly allow important AI/search crawlers.", -5))

    if crawl_data.get("sitemap_reachable"):
        score += 10
        findings.append(_pass("Sitemap reachable", "An XML sitemap was found.", 10))
    else:
        findings.append(_fail("medium", "No XML sitemap found", "No sitemap was reachable at common locations.", "Generate an XML sitemap and link it from robots.txt.", -10))

    if crawl_data.get("has_canonical"):
        score += 10
        findings.append(_pass("Canonical tag present", "The homepage has a canonical URL.", 10))
    else:
        findings.append(_fail("low", "No canonical tag", "No canonical link tag was found on the homepage.", "Add a canonical tag to reduce duplicate URL ambiguity.", -5))

    error_rate = crawl_data.get("error_rate", 0)
    if error_rate == 0:
        score += 20
        findings.append(_pass("No broken pages found", "Crawled pages returned successful responses.", 20))
    elif error_rate < 0.1:
        score += 10
        findings.append(_fail("medium", "Some broken pages", f"{error_rate * 100:.0f}% of crawled pages returned errors.", "Fix 4xx/5xx pages or redirect removed URLs.", -10))
    else:
        findings.append(_fail("high", "High broken-page rate", f"{error_rate * 100:.0f}% of crawled pages returned errors.", "Prioritize fixing broken internal URLs.", -20))

    return _result(score, findings)


def score_schema(schema_data: dict) -> dict:
    findings = []
    score = 0.0
    detected = set(schema_data.get("types_detected", []))

    checks = [
        ("Organization", 15, "high", "Organization schema helps AI understand the entity behind the site.", "Add Organization JSON-LD with name, url, logo, contactPoint, and sameAs profiles."),
        ("WebSite", 10, "medium", "WebSite schema helps AI understand the site and search behavior.", "Add WebSite JSON-LD, including SearchAction if relevant."),
        ("FAQPage", 25, "critical", "FAQPage schema is highly compatible with answer-engine citations.", "Add FAQPage JSON-LD to pages that answer common questions."),
        ("Article", 15, "high", "Article or BlogPosting schema marks editorial content clearly.", "Add Article or BlogPosting schema to articles with author and dates."),
        ("BreadcrumbList", 10, "medium", "Breadcrumbs clarify site structure.", "Add BreadcrumbList schema to inner pages."),
        ("HowTo", 15, "medium", "HowTo schema makes instructional content easier to quote.", "Add HowTo schema to step-by-step guides."),
        ("AggregateRating", 10, "low", "Review/rating schema can add trust context.", "Add AggregateRating only where genuine reviews exist."),
    ]

    for schema_type, points, severity, description, recommendation in checks:
        if schema_type in detected or (schema_type == "Article" and "BlogPosting" in detected):
            score += points
            findings.append(_pass(f"{schema_type} schema detected", f"{schema_type} structured data was found.", points))
        else:
            findings.append(_fail(severity, f"Missing {schema_type} schema", description, recommendation, -points))

    return _result(score, findings)


def score_eeat(crawl_data: dict) -> dict:
    checks = [
        ("has_about_page", 15, "high", "No About page was found.", "Create an About page explaining your expertise, credentials, team, and mission.", "About page present"),
        ("has_author_bios", 20, "critical", "No author bios were detected.", "Add author bio sections with credentials to editorial pages.", "Author bios present"),
        ("has_contact_page", 15, "high", "No contact page or contact information was found.", "Add a Contact page with email, phone, address, or support details.", "Contact information present"),
        ("has_privacy_policy", 10, "medium", "No privacy policy was found.", "Publish a clear Privacy Policy page.", "Privacy policy present"),
        ("has_terms", 5, "low", "No terms page was found.", "Add Terms of Service or Terms of Use.", "Terms page present"),
        ("has_external_authority_links", 15, "high", "Content does not cite authoritative external sources.", "Link to credible sources such as government pages, standards, research, or recognized publications.", "Authority links present"),
        ("has_visible_dates", 10, "medium", "No visible publish/update dates were found.", "Show publish and last-updated dates on content pages.", "Content dates visible"),
        ("has_social_links", 10, "medium", "No official social links were found.", "Link verified brand profiles from the header, footer, or About page.", "Social links present"),
    ]
    return _score_boolean_checks(crawl_data, checks)


def score_content(crawl_data: dict) -> dict:
    findings = []
    score = 0.0

    avg_word_count = crawl_data.get("avg_word_count", 0)
    if avg_word_count >= 1500:
        score += 20
        findings.append(_pass("Deep content", f"Average page word count is {avg_word_count}.", 20))
    elif avg_word_count >= 800:
        score += 12
        findings.append(_fail("medium", "Moderate content depth", f"Average page word count is {avg_word_count}.", "Expand key pages with examples, evidence, comparisons, and original insights.", -8))
    else:
        findings.append(_fail("critical", "Thin content", f"Average page word count is {avg_word_count}.", "Expand important pages so they answer the topic thoroughly.", -20))

    checks = [
        ("has_faq_sections", 20, "critical", "No FAQ or Q&A sections were found.", "Add concise FAQ sections to important pages.", "FAQ/Q&A sections found"),
        ("has_proper_headings", 15, "medium", "Heading structure is weak or inconsistent.", "Use one H1, then clear H2/H3 sections that map to user questions.", "Proper heading hierarchy"),
        ("has_direct_answer_format", 15, "high", "Content does not lead with direct answers.", "Start key sections with a short answer, then provide detail and proof.", "Direct answer format"),
    ]
    boolean_result = _score_boolean_checks(crawl_data, checks)
    score += boolean_result["score"]
    findings.extend(boolean_result["findings"])

    days = crawl_data.get("days_since_last_update", 999)
    if days <= 90:
        score += 20
        findings.append(_pass("Fresh content", f"Content appears updated {days} days ago.", 20))
    elif days <= 180:
        score += 12
        findings.append(_fail("medium", "Content moderately fresh", f"Last visible update appears {days} days ago.", "Refresh key pages at least quarterly.", -8))
    else:
        findings.append(_fail("high", "Stale content", "Content appears older than six months or has no visible update date.", "Update facts, examples, screenshots, and visible modified dates.", -20))

    pages = crawl_data.get("pages_crawled", 0)
    if pages >= 20:
        score += 10
        findings.append(_pass("Good content depth", f"{pages} pages were discovered.", 10))
    elif pages >= 5:
        score += 5
        findings.append(_fail("low", "Limited content volume", f"Only {pages} pages were discovered.", "Add focused FAQ, comparison, glossary, and how-to pages.", -5))
    else:
        findings.append(_fail("medium", "Very few pages", f"Only {pages} pages were found.", "Publish more useful pages around your primary customer questions.", -10))

    return _result(score, findings)


def score_authority(crawl_data: dict) -> dict:
    findings = []
    score = 0.0

    if crawl_data.get("has_social_presence"):
        score += 20
        findings.append(_pass("Social presence verified", "Social presence verified detected.", 20))
    else:
        findings.append(_fail("high", "Missing: Social presence verified", "No social media presence was detected.", "Create or link official profiles on LinkedIn, X, YouTube, or relevant industry platforms.", -20))

    external_checked = crawl_data.get("authority_external_checked")
    external_data = crawl_data.get("authority_external_data", {})
    external_checks = [
        ("has_wikipedia_mention", "wikipedia", 25, "medium", "No Wikipedia or Wikidata signal was found in external search results.", "If notable, build a Wikidata entity or earn neutral third-party references.", "Wikipedia/Wikidata signal"),
        ("has_directory_listing", "directory", 20, "high", "No major directory/profile signal was found in external search results.", "Claim profiles on Google Business Profile, Bing Places, LinkedIn, Crunchbase, G2, Clutch, or industry directories.", "Directory/profile signals found"),
        ("has_press_mentions", "press", 20, "medium", "No press or news signal was found in external search results.", "Publish a newsroom and pursue credible third-party mentions.", "Press/news signals found"),
    ]

    if external_checked:
        for field, signal_key, points, severity, fail_desc, recommendation, pass_title in external_checks:
            signal_data = external_data.get(signal_key, {})
            if crawl_data.get(field):
                score += points
                findings.append(_pass(pass_title, f"{pass_title} detected from external search or site content.", points))
            elif signal_data and not signal_data.get("checked", True):
                findings.append(_fail(
                    "low",
                    f"{pass_title} not verified",
                    "The external lookup for this authority signal did not complete, so this scan cannot confirm whether the signal exists.",
                    "Retry the scan after provider access is available, or add a Brave Search key with enough quota.",
                    0,
                ))
            else:
                findings.append(_fail(severity, f"Missing: {pass_title}", fail_desc, recommendation, -points))
    else:
        findings.append(_fail(
            "low",
            "External authority search not configured",
            "Wikipedia, directory, and press signals were not externally verified because BRAVE_SEARCH_API_KEY is not configured.",
            "Add BRAVE_SEARCH_API_KEY to verify external authority signals instead of relying only on crawled page text.",
            0,
        ))

    domain_age_years = crawl_data.get("domain_age_years", 0)
    if domain_age_years >= 5:
        score += 15
        findings.append(_pass("Established domain", f"Domain appears {domain_age_years} years old.", 15))
    elif domain_age_years >= 2:
        score += 8
        findings.append(_fail("low", "Relatively new domain", f"Domain age signal is only {domain_age_years} years.", "Compensate with strong brand mentions, citations, and directory listings.", -7))
    else:
        if crawl_data.get("authority_external_data", {}).get("domain_age_checked") is False:
            findings.append(_fail("low", "Domain age not verified", "Domain age could not be verified through RDAP.", "This is a measurement gap, not proof that the domain is new.", 0))
        else:
            findings.append(_fail("medium", "No domain age authority signal", "Domain age could not be verified.", "Add stronger third-party entity signals while the domain gains history.", -15))

    return _result(score, findings)


def calculate_overall_score(dimension_scores: dict) -> tuple[float, str]:
    overall = sum(dimension_scores[key] * weight for key, weight in SCORING_WEIGHTS.items())
    if overall >= 90:
        grade = "A"
    elif overall >= 80:
        grade = "B"
    elif overall >= 70:
        grade = "C"
    elif overall >= 60:
        grade = "D"
    else:
        grade = "F"
    return round(overall, 1), grade


def _score_boolean_checks(data, checks):
    findings = []
    score = 0.0
    for field, points, severity, fail_desc, recommendation, pass_title in checks:
        if data.get(field):
            score += points
            findings.append(_pass(pass_title, f"{pass_title} detected.", points))
        else:
            findings.append(_fail(severity, f"Missing: {pass_title}", fail_desc, recommendation, -points))
    return _result(score, findings)


def _result(score, findings):
    return {"score": min(round(score, 1), 100.0), "findings": findings}


def _pass(title, description, points):
    return {
        "title": title,
        "description": description,
        "recommendation": "",
        "severity": "pass",
        "points_impact": points,
        "is_passed": True,
    }


def _fail(severity, title, description, recommendation, points_impact):
    return {
        "title": title,
        "description": description,
        "recommendation": recommendation,
        "severity": severity,
        "points_impact": points_impact,
        "is_passed": False,
    }
