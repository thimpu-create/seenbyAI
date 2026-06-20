# AI Visibility Audit Tool — Full Product & Technical Specification
> Hand this document to your coding agent (Aider, Claude Code, etc.) as the single source of truth.

---

## 1. The Problem (Deep Dive)

### What Changed
Google's I/O 2026 overhaul transformed search from a link-delivery system into an AI answer engine.
Instead of showing 10 blue links, Google now generates a conversational AI answer at the top — and
only cites 2–4 sources inside it. For a business or publisher, getting cited in that AI answer is
the new "ranking #1."

### Why Businesses Are Blind
Traditional SEO tools (Ahrefs, SEMrush, Moz) track keyword rankings and backlinks — metrics that
no longer map to AI citation visibility. A business could rank #1 for a keyword and still never
appear in the AI answer. Nobody is telling them:

- **Am I being cited by Google AI, Perplexity, or ChatGPT?**
- **Why am I NOT being cited?**
- **What exactly do I need to fix to get cited?**
- **Are my competitors being cited instead of me?**

### The 5 Core Pain Points

| # | Pain Point | Who Feels It | Severity |
|---|---|---|---|
| 1 | Can't tell if they appear in AI answers | Every business with a website | 🔴 Critical |
| 2 | Don't understand E-E-A-T or schema markup | SMBs, bloggers | 🔴 Critical |
| 3 | Old SEO agency gives outdated advice | SMBs paying agencies | 🟠 High |
| 4 | Traffic dropped but no diagnosis | Publishers, e-commerce | 🔴 Critical |
| 5 | No way to monitor AI citation over time | All businesses | 🟠 High |

---

## 2. The Solution

**AI Visibility Audit Tool** — A SaaS web app where a user enters their website URL, and the
system:

1. **Crawls** the website and analyzes it across 5 scoring dimensions
2. **Queries** real AI engines (Perplexity, OpenAI) with business-relevant questions and checks
   if the site gets cited
3. **Scores** the site with an overall AI Citability Score (0–100)
4. **Explains** every deduction in plain English
5. **Recommends** a prioritized fix list
6. **Monitors** the site weekly and alerts the user to changes

---

## 3. Tech Stack

```
Backend:        Django 5.x + Django REST Framework
Database:       PostgreSQL 16
Cache/Broker:   Redis 7
Task Queue:     Celery 5
HTTP Client:    httpx (async)
HTML Parsing:   BeautifulSoup4 + lxml
Headless Browser: Playwright (for JS-rendered pages)
AI APIs:        OpenAI Python SDK, Perplexity (httpx)
Search API:     Serper.dev (Google AI Overview data)
PDF Reports:    WeasyPrint
Frontend:       Django Templates + Tailwind CSS (CDN) + HTMX
Auth:           django-allauth
Env Vars:       python-decouple
Deployment:     Docker + docker-compose
```

### Key Third-Party APIs Required
| Service | Purpose | Free Tier |
|---|---|---|
| `serper.dev` | Google search results + AI Overview data | 2,500 free queries |
| `openai.com` | Query ChatGPT, check if site is cited | Pay-per-use |
| `api.perplexity.ai` | Query Perplexity, check if site is cited | Pay-per-use |

---

## 4. Project Structure

```
aivisibility/
├── manage.py
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── config/
│   ├── __init__.py
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   ├── wsgi.py
│   └── celery.py
├── apps/
│   ├── accounts/          # User auth, profiles, billing tier
│   ├── audits/            # Core audit logic, models, views
│   ├── crawler/           # Website crawling engine
│   ├── scorer/            # Scoring engine (5 dimensions)
│   ├── citation_checker/  # AI engine citation checking
│   ├── recommendations/   # Recommendation generation
│   ├── reports/           # PDF report generation
│   └── monitoring/        # Scheduled re-audits + alerts
├── templates/
│   ├── base.html
│   ├── dashboard/
│   ├── audits/
│   └── reports/
└── static/
    ├── css/
    └── js/
```

---

## 5. Data Models

### `accounts/models.py`

```python
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    TIER_FREE = 'free'
    TIER_PRO = 'pro'
    TIER_AGENCY = 'agency'
    TIER_CHOICES = [
        (TIER_FREE, 'Free'),
        (TIER_PRO, 'Pro'),
        (TIER_AGENCY, 'Agency'),
    ]
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default=TIER_FREE)
    audits_used_this_month = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    # Tier limits
    TIER_LIMITS = {
        TIER_FREE: 3,
        TIER_PRO: 50,
        TIER_AGENCY: 500,
    }

    def can_run_audit(self):
        return self.audits_used_this_month < self.TIER_LIMITS[self.tier]
```

### `audits/models.py`

```python
import uuid
from django.db import models
from django.conf import settings


class Website(models.Model):
    """A website being tracked by a user."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='websites')
    url = models.URLField(max_length=500)
    domain = models.CharField(max_length=255)  # extracted from url
    name = models.CharField(max_length=255, blank=True)
    monitoring_enabled = models.BooleanField(default=False)
    monitoring_frequency = models.CharField(
        max_length=20,
        choices=[('weekly', 'Weekly'), ('monthly', 'Monthly')],
        default='weekly'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'domain')


class AuditReport(models.Model):
    """One complete audit run for a website."""
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETE = 'complete'
    STATUS_FAILED = 'failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name='audits')
    status = models.CharField(max_length=20, default=STATUS_PENDING)
    triggered_by = models.CharField(
        max_length=20,
        choices=[('manual', 'Manual'), ('scheduled', 'Scheduled')],
        default='manual'
    )

    # Overall score
    overall_score = models.FloatField(null=True, blank=True)
    score_grade = models.CharField(max_length=2, blank=True)  # A, B, C, D, F

    # Individual dimension scores (0.0 - 100.0)
    score_technical = models.FloatField(null=True, blank=True)
    score_schema = models.FloatField(null=True, blank=True)
    score_eeat = models.FloatField(null=True, blank=True)
    score_content = models.FloatField(null=True, blank=True)
    score_authority = models.FloatField(null=True, blank=True)

    # Raw data (JSON blobs)
    crawl_data = models.JSONField(default=dict)       # raw crawled page data
    citation_data = models.JSONField(default=dict)    # AI citation check results
    schema_data = models.JSONField(default=dict)      # detected schema types
    technical_data = models.JSONField(default=dict)   # technical checks

    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class AuditFinding(models.Model):
    """Individual finding/issue from an audit."""
    SEVERITY_CRITICAL = 'critical'
    SEVERITY_HIGH = 'high'
    SEVERITY_MEDIUM = 'medium'
    SEVERITY_LOW = 'low'
    SEVERITY_PASS = 'pass'

    DIMENSION_TECHNICAL = 'technical'
    DIMENSION_SCHEMA = 'schema'
    DIMENSION_EEAT = 'eeat'
    DIMENSION_CONTENT = 'content'
    DIMENSION_AUTHORITY = 'authority'

    audit = models.ForeignKey(AuditReport, on_delete=models.CASCADE, related_name='findings')
    dimension = models.CharField(max_length=20)
    severity = models.CharField(max_length=20)
    title = models.CharField(max_length=255)
    description = models.TextField()         # What's wrong / what was found
    recommendation = models.TextField()      # Exactly how to fix it
    points_impact = models.FloatField()      # How many points this costs (-ve) or gives (+ve)
    is_passed = models.BooleanField(default=False)

    class Meta:
        ordering = ['dimension', '-points_impact']


class CitationCheck(models.Model):
    """Result of querying an AI engine to check if the website was cited."""
    audit = models.ForeignKey(AuditReport, on_delete=models.CASCADE,
                              related_name='citation_checks')

    AI_ENGINE_GOOGLE = 'google'
    AI_ENGINE_PERPLEXITY = 'perplexity'
    AI_ENGINE_CHATGPT = 'chatgpt'

    ai_engine = models.CharField(max_length=30)
    query_used = models.TextField()         # the question asked
    was_cited = models.BooleanField(default=False)
    citation_url = models.URLField(blank=True)
    ai_response_snippet = models.TextField(blank=True)   # first 500 chars of AI answer
    checked_at = models.DateTimeField(auto_now_add=True)


class MonitoringAlert(models.Model):
    """Alert sent when monitoring detects a change."""
    website = models.ForeignKey(Website, on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(
        max_length=30,
        choices=[
            ('score_drop', 'Score Dropped'),
            ('score_rise', 'Score Improved'),
            ('citation_gained', 'New AI Citation'),
            ('citation_lost', 'Lost AI Citation'),
        ]
    )
    message = models.TextField()
    old_value = models.FloatField(null=True)
    new_value = models.FloatField(null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
```

---

## 6. Scoring Engine

### Dimensions & Weights

```python
SCORING_WEIGHTS = {
    'technical':  0.15,
    'schema':     0.20,
    'eeat':       0.25,
    'content':    0.25,
    'authority':  0.15,
}
```

### `scorer/engine.py` — Full Scoring Logic

```python
"""
Scoring engine. Each dimension returns a dict:
{
    'score': float,            # 0.0 - 100.0
    'findings': [
        {
            'title': str,
            'description': str,
            'recommendation': str,
            'severity': 'critical' | 'high' | 'medium' | 'low' | 'pass',
            'points_impact': float,
            'is_passed': bool,
        }
    ]
}
"""
from urllib.parse import urljoin
import re


# ── DIMENSION 1: TECHNICAL (15%) ─────────────────────────────────────────────

def score_technical(crawl_data: dict) -> dict:
    """
    Checks:
    - HTTPS (20 pts)
    - Response time < 3s (15 pts)
    - Viewport meta tag present (15 pts)
    - robots.txt reachable (10 pts)
    - sitemap.xml reachable (10 pts)
    - Canonical tag on homepage (10 pts)
    - No 4xx/5xx errors on crawled pages (20 pts)
    Total: 100 pts
    """
    findings = []
    score = 0.0

    # HTTPS check
    if crawl_data.get('uses_https'):
        score += 20
        findings.append(_pass('Uses HTTPS', 'Site is served over HTTPS.', 20))
    else:
        findings.append(_fail(
            'critical', 'Not using HTTPS',
            'Your site is not served over HTTPS. AI engines treat HTTPS as a baseline trust signal.',
            'Obtain an SSL certificate (free via Let\'s Encrypt) and redirect all HTTP traffic to HTTPS.',
            -20
        ))

    # Response time
    response_ms = crawl_data.get('response_time_ms', 9999)
    if response_ms < 3000:
        score += 15
        findings.append(_pass('Fast response time', f'Homepage responded in {response_ms}ms.', 15))
    else:
        findings.append(_fail(
            'medium', 'Slow page response',
            f'Homepage took {response_ms}ms to respond. Slow pages signal poor quality.',
            'Optimize server response time, use a CDN, enable compression.',
            -10
        ))

    # Viewport meta
    if crawl_data.get('has_viewport_meta'):
        score += 15
        findings.append(_pass('Mobile viewport meta present', 'Page is mobile-friendly.', 15))
    else:
        findings.append(_fail(
            'high', 'Missing viewport meta tag',
            'No <meta name="viewport"> tag found. Site may not be mobile-friendly.',
            'Add <meta name="viewport" content="width=device-width, initial-scale=1"> to <head>.',
            -15
        ))

    # robots.txt
    if crawl_data.get('robots_txt_reachable'):
        score += 10
        findings.append(_pass('robots.txt reachable', 'robots.txt is accessible.', 10))
    else:
        findings.append(_fail(
            'low', 'Missing robots.txt',
            'No robots.txt found. AI crawlers use this to understand crawl permissions.',
            'Create a /robots.txt file. At minimum: User-agent: * Allow: /',
            -5
        ))

    # sitemap.xml
    if crawl_data.get('sitemap_reachable'):
        score += 10
        findings.append(_pass('sitemap.xml present', 'XML sitemap is accessible.', 10))
    else:
        findings.append(_fail(
            'medium', 'No XML sitemap found',
            'No sitemap.xml found. AI crawlers use sitemaps to discover content.',
            'Generate an XML sitemap and link it from robots.txt.',
            -10
        ))

    # Canonical tag
    if crawl_data.get('has_canonical'):
        score += 10
        findings.append(_pass('Canonical tag present', 'Homepage has a canonical URL.', 10))
    else:
        findings.append(_fail(
            'low', 'No canonical tag',
            'No <link rel="canonical"> on the homepage.',
            'Add a canonical tag to prevent duplicate content confusion.',
            -5
        ))

    # Error rate
    error_rate = crawl_data.get('error_rate', 0)
    if error_rate == 0:
        score += 20
        findings.append(_pass('No broken pages', 'All crawled pages returned 200 OK.', 20))
    elif error_rate < 0.1:
        score += 10
        findings.append(_fail('medium', 'Some broken pages',
            f'{error_rate*100:.0f}% of crawled pages returned errors.',
            'Fix all 4xx and 5xx pages. Use a redirect for removed pages.',
            -10))
    else:
        findings.append(_fail('high', 'High rate of broken pages',
            f'{error_rate*100:.0f}% of crawled pages returned errors.',
            'Audit and fix all broken pages immediately.',
            -20))

    return {'score': min(score, 100.0), 'findings': findings}


# ── DIMENSION 2: SCHEMA MARKUP (20%) ─────────────────────────────────────────

def score_schema(schema_data: dict) -> dict:
    """
    Checks:
    - Organization schema (15 pts)
    - WebSite schema (10 pts)
    - FAQPage schema (25 pts) ← most important for AI citation
    - Article / NewsArticle (15 pts)
    - BreadcrumbList (10 pts)
    - HowTo (15 pts)
    - AggregateRating / Review (10 pts)
    Total: 100 pts
    """
    findings = []
    score = 0.0
    detected = schema_data.get('types_detected', [])

    checks = [
        ('Organization', 15, 'high',
         'AI engines use Organization schema to understand who you are, your name, logo, and contact info.',
         'Add Organization JSON-LD schema to your homepage. Include: name, url, logo, contactPoint, sameAs (social profiles).'),
        ('WebSite', 10, 'medium',
         'WebSite schema helps AI understand your site\'s search functionality.',
         'Add WebSite JSON-LD schema with SearchAction to enable sitelinks search.'),
        ('FAQPage', 25, 'critical',
         'FAQPage schema is the single most impactful schema for AI citations. AI engines pull FAQ answers directly.',
         'Add FAQPage JSON-LD to any page with Q&A content. Format: {"@type":"FAQPage","mainEntity":[{"@type":"Question","name":"Q?","acceptedAnswer":{"@type":"Answer","text":"A."}}]}'),
        ('Article', 15, 'high',
         'Article schema marks your content as authoritative editorial content, increasing citation likelihood.',
         'Add Article or BlogPosting JSON-LD to all article/blog pages. Include: author, datePublished, dateModified.'),
        ('BreadcrumbList', 10, 'medium',
         'Breadcrumbs help AI understand your site structure.',
         'Add BreadcrumbList schema to all inner pages.'),
        ('HowTo', 15, 'medium',
         'HowTo schema surfaces step-by-step content directly in AI answers.',
         'Add HowTo JSON-LD to any instructional content.'),
        ('AggregateRating', 10, 'low',
         'Rating schema adds trust signals AI engines look for.',
         'Add AggregateRating schema if your site has reviews.'),
    ]

    for schema_type, points, severity, description, recommendation in checks:
        if schema_type in detected:
            score += points
            findings.append(_pass(f'{schema_type} schema detected',
                                  f'{schema_type} structured data found on the site.', points))
        else:
            findings.append(_fail(
                severity,
                f'Missing {schema_type} schema',
                description,
                recommendation,
                -points
            ))

    return {'score': min(score, 100.0), 'findings': findings}


# ── DIMENSION 3: E-E-A-T (25%) ───────────────────────────────────────────────

def score_eeat(crawl_data: dict) -> dict:
    """
    Experience, Expertise, Authoritativeness, Trustworthiness.
    Checks:
    - About page present (15 pts)
    - Author bios on articles (20 pts)
    - Contact page / contact info (15 pts)
    - Privacy policy page (10 pts)
    - Terms of service page (5 pts)
    - External links to authoritative sources (15 pts)
    - Date/last modified visible on content (10 pts)
    - Social media profile links present (10 pts)
    Total: 100 pts
    """
    findings = []
    score = 0.0

    checks = [
        ('has_about_page', 15, 'high',
         'No About page found.',
         'AI engines look for an About page to verify who is behind the site. Create one that describes your expertise, credentials, and mission.',
         'About page present'),
        ('has_author_bios', 20, 'critical',
         'No author bios detected on article/blog pages.',
         'Add author bio sections to all content pages. Include: author name, credentials, headshot, and links to social profiles or other published work.',
         'Author bios present'),
        ('has_contact_page', 15, 'high',
         'No contact page or contact information found.',
         'Add a Contact page with email, phone, or physical address. This is a core trust signal for AI engines.',
         'Contact information present'),
        ('has_privacy_policy', 10, 'medium',
         'No privacy policy page found.',
         'Create a Privacy Policy page. Required by law in most regions and used as a trust signal.',
         'Privacy policy present'),
        ('has_terms', 5, 'low',
         'No terms of service/use page found.',
         'Add a Terms of Service page for additional trust signals.',
         'Terms of service present'),
        ('has_external_authority_links', 15, 'high',
         'Content does not link to authoritative external sources.',
         'Add citations to your content — link to government sites (.gov), research papers, or established news sources. AI engines value content that cites its sources.',
         'Links to authoritative external sources'),
        ('has_visible_dates', 10, 'medium',
         'No publish/update dates visible on content pages.',
         'Display the publish date and last modified date on all articles. AI engines heavily weight fresh, dated content.',
         'Content dates visible'),
        ('has_social_links', 10, 'medium',
         'No social media profile links found on the site.',
         'Add links to your official social media profiles in the header or footer. This helps AI verify your entity across platforms.',
         'Social media links present'),
    ]

    for field, points, severity, fail_desc, recommendation, pass_title in checks:
        if crawl_data.get(field):
            score += points
            findings.append(_pass(pass_title, f'{pass_title} detected.', points))
        else:
            findings.append(_fail(severity, f'Missing: {pass_title}',
                                  fail_desc, recommendation, -points))

    return {'score': min(score, 100.0), 'findings': findings}


# ── DIMENSION 4: CONTENT QUALITY (25%) ───────────────────────────────────────

def score_content(crawl_data: dict) -> dict:
    """
    Checks:
    - Average word count of key pages (20 pts)
    - FAQ or Q&A sections in content (20 pts)
    - Proper H1/H2/H3 heading hierarchy (15 pts)
    - Freshness: content updated in last 6 months (20 pts)
    - Direct answer format: short, clear first paragraph (15 pts)
    - Number of pages crawled / content depth (10 pts)
    Total: 100 pts
    """
    findings = []
    score = 0.0

    avg_word_count = crawl_data.get('avg_word_count', 0)
    if avg_word_count >= 1500:
        score += 20
        findings.append(_pass('Deep content', f'Average page word count: {avg_word_count}', 20))
    elif avg_word_count >= 800:
        score += 12
        findings.append(_fail('medium', 'Moderate content depth',
            f'Average page word count is {avg_word_count}. Aim for 1,500+ words on key pages.',
            'Expand thin content with more depth, examples, case studies, and original insights.',
            -8))
    else:
        findings.append(_fail('critical', 'Thin content',
            f'Average page word count is only {avg_word_count}. AI engines rarely cite thin content.',
            'Significantly expand your content. Each key page should be 1,500+ words with depth and original insight.',
            -20))

    if crawl_data.get('has_faq_sections'):
        score += 20
        findings.append(_pass('FAQ/Q&A sections found',
            'Content includes question-and-answer formatted sections. This is the #1 content pattern for AI citation.', 20))
    else:
        findings.append(_fail('critical', 'No FAQ or Q&A content sections',
            'AI engines are trained on Q&A patterns. Content without FAQ sections is less likely to be cited.',
            'Add a "Frequently Asked Questions" section to your most important pages. Write clear questions + concise 2-3 sentence answers.',
            -20))

    if crawl_data.get('has_proper_headings'):
        score += 15
        findings.append(_pass('Proper heading hierarchy', 'H1/H2/H3 structure is well-organized.', 15))
    else:
        findings.append(_fail('medium', 'Poor heading structure',
            'Pages are missing a clear H1/H2/H3 hierarchy. AI uses headings to understand content structure.',
            'Every page should have exactly one H1 (the page title), followed by H2s for main sections and H3s for subsections.',
            -15))

    days_since_update = crawl_data.get('days_since_last_update', 999)
    if days_since_update <= 90:
        score += 20
        findings.append(_pass('Fresh content', f'Content updated {days_since_update} days ago.', 20))
    elif days_since_update <= 180:
        score += 12
        findings.append(_fail('medium', 'Content moderately fresh',
            f'Last update was {days_since_update} days ago. AI engines prefer recently updated content.',
            'Review and update your key pages at least quarterly. Even minor updates with new data or insights count.',
            -8))
    else:
        findings.append(_fail('high', 'Stale content',
            f'Content appears not to have been updated in {days_since_update}+ days.',
            'Audit all key pages. Update statistics, add new sections, and refresh publication dates on updated content.',
            -20))

    if crawl_data.get('has_direct_answer_format'):
        score += 15
        findings.append(_pass('Direct answer format', 'Content uses clear, direct answer formatting.', 15))
    else:
        findings.append(_fail('high', 'Content lacks direct answer format',
            'Content uses dense paragraphs without clear, direct answers to likely user questions.',
            'Rewrite key sections to directly answer questions. Lead with the answer in the first sentence, then elaborate.',
            -15))

    pages_crawled = crawl_data.get('pages_crawled', 0)
    if pages_crawled >= 20:
        score += 10
        findings.append(_pass('Good content depth', f'{pages_crawled} pages crawled.', 10))
    elif pages_crawled >= 5:
        score += 5
        findings.append(_fail('low', 'Limited content volume',
            f'Only {pages_crawled} pages discovered. More quality content = more citation opportunities.',
            'Consider adding more pages: FAQs, blog posts, how-to guides, glossaries.',
            -5))
    else:
        findings.append(_fail('medium', 'Very few pages',
            f'Only {pages_crawled} pages found. Very limited content surface area for AI citation.',
            'Expand your site with targeted content. Each page is a new opportunity to be cited.',
            -10))

    return {'score': min(score, 100.0), 'findings': findings}


# ── DIMENSION 5: BRAND AUTHORITY (15%) ───────────────────────────────────────

def score_authority(crawl_data: dict) -> dict:
    """
    Checks:
    - Domain age (15 pts)
    - Social media presence detected (20 pts)
    - Wikipedia / Wikidata mention (25 pts)
    - Business directory listing (Google, Yelp, etc.) (20 pts)
    - News / press mentions found (20 pts)
    Total: 100 pts
    """
    findings = []
    score = 0.0

    domain_age_years = crawl_data.get('domain_age_years', 0)
    if domain_age_years >= 5:
        score += 15
        findings.append(_pass('Established domain', f'Domain is {domain_age_years} years old.', 15))
    elif domain_age_years >= 2:
        score += 8
        findings.append(_fail('low', 'Relatively new domain',
            f'Domain is only {domain_age_years} years old. Newer domains carry less authority.',
            'Focus on building brand mentions and backlinks to accelerate trust building.',
            -7))
    else:
        findings.append(_fail('medium', 'Very new domain',
            f'Domain is less than 2 years old. Brand new domains are rarely cited by AI engines.',
            'Build your brand presence actively: get listed in directories, earn press mentions, publish guest posts.',
            -15))

    if crawl_data.get('has_social_presence'):
        score += 20
        findings.append(_pass('Social media presence verified',
            'Social media profiles linked from the site.', 20))
    else:
        findings.append(_fail('high', 'No social media presence detected',
            'No social media profiles linked from the site. AI engines cross-reference social signals for entity verification.',
            'Create profiles on LinkedIn, Twitter/X, and relevant industry platforms. Link them from your website footer.',
            -20))

    if crawl_data.get('has_wikipedia_mention'):
        score += 25
        findings.append(_pass('Wikipedia/Wikidata mention',
            'Entity found on Wikipedia or Wikidata — strongest possible authority signal.', 25))
    else:
        findings.append(_fail('medium', 'No Wikipedia/Wikidata presence',
            'No Wikipedia or Wikidata entry found. Wikipedia is the highest-trust source AI engines use.',
            'If notable enough, create a Wikipedia page. At minimum, create a Wikidata entity for your organization.',
            -20))

    if crawl_data.get('has_directory_listing'):
        score += 20
        findings.append(_pass('Business directory listings found',
            'Business found in online directories (Google Business, Yelp, etc.).', 20))
    else:
        findings.append(_fail('high', 'No business directory listings',
            'Business not found in major online directories.',
            'Create/claim your Google Business Profile and list on Yelp, Bing Places, and industry-specific directories.',
            -20))

    if crawl_data.get('has_press_mentions'):
        score += 20
        findings.append(_pass('Press/news mentions found',
            'Brand mentioned in news or press articles.', 20))
    else:
        findings.append(_fail('medium', 'No press or news mentions',
            'No press coverage found. AI engines value entities mentioned in news sources.',
            'Pursue PR: write press releases, reach out to journalists, offer expert commentary to publications.',
            -15))

    return {'score': min(score, 100.0), 'findings': findings}


# ── AGGREGATOR ────────────────────────────────────────────────────────────────

def calculate_overall_score(dimension_scores: dict) -> tuple[float, str]:
    """Calculate weighted overall score and grade."""
    weights = {
        'technical': 0.15,
        'schema': 0.20,
        'eeat': 0.25,
        'content': 0.25,
        'authority': 0.15,
    }
    overall = sum(dimension_scores[k] * weights[k] for k in weights)
    grade = 'F'
    if overall >= 90: grade = 'A'
    elif overall >= 80: grade = 'B'
    elif overall >= 70: grade = 'C'
    elif overall >= 60: grade = 'D'
    return round(overall, 1), grade


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _pass(title, description, points):
    return {
        'title': title, 'description': description,
        'recommendation': '', 'severity': 'pass',
        'points_impact': points, 'is_passed': True
    }

def _fail(severity, title, description, recommendation, points_impact):
    return {
        'title': title, 'description': description,
        'recommendation': recommendation, 'severity': severity,
        'points_impact': points_impact, 'is_passed': False
    }
```

---

## 7. Crawler

### `crawler/engine.py`

```python
"""
Crawls a website and returns a normalized crawl_data dict
that the scoring engine consumes.
"""
import asyncio
import time
from urllib.parse import urlparse, urljoin
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup


MAX_PAGES = 30
TIMEOUT = 10


async def crawl_website(url: str) -> dict:
    """Main entry point. Returns crawl_data dict."""
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    data = {
        # Technical
        'uses_https': parsed.scheme == 'https',
        'response_time_ms': None,
        'has_viewport_meta': False,
        'robots_txt_reachable': False,
        'sitemap_reachable': False,
        'has_canonical': False,
        'error_rate': 0.0,
        # E-E-A-T
        'has_about_page': False,
        'has_author_bios': False,
        'has_contact_page': False,
        'has_privacy_policy': False,
        'has_terms': False,
        'has_external_authority_links': False,
        'has_visible_dates': False,
        'has_social_links': False,
        # Content
        'avg_word_count': 0,
        'has_faq_sections': False,
        'has_proper_headings': False,
        'days_since_last_update': 999,
        'has_direct_answer_format': False,
        'pages_crawled': 0,
        # Authority
        'domain_age_years': 0,
        'has_social_presence': False,
        'has_wikipedia_mention': False,
        'has_directory_listing': False,
        'has_press_mentions': False,
        # Meta
        'page_titles': [],
        'meta_descriptions': [],
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=TIMEOUT) as client:
        # Homepage
        try:
            start = time.monotonic()
            resp = await client.get(url)
            data['response_time_ms'] = int((time.monotonic() - start) * 1000)
            soup = BeautifulSoup(resp.text, 'lxml')
            _parse_homepage(soup, base_url, data)
        except Exception as e:
            data['error_message'] = str(e)
            return data

        # robots.txt
        try:
            r = await client.get(f"{base_url}/robots.txt")
            data['robots_txt_reachable'] = r.status_code == 200
        except:
            pass

        # sitemap.xml
        try:
            r = await client.get(f"{base_url}/sitemap.xml")
            data['sitemap_reachable'] = r.status_code == 200
        except:
            pass

        # Crawl internal links
        links = _extract_internal_links(soup, base_url)
        visited = {url}
        word_counts = []
        error_count = 0

        for link in links[:MAX_PAGES]:
            if link in visited:
                continue
            visited.add(link)
            try:
                r = await client.get(link)
                if r.status_code >= 400:
                    error_count += 1
                    continue
                page_soup = BeautifulSoup(r.text, 'lxml')
                _parse_page(page_soup, link, base_url, data)
                wc = len(page_soup.get_text().split())
                word_counts.append(wc)
            except:
                error_count += 1

        data['pages_crawled'] = len(visited)
        data['avg_word_count'] = int(sum(word_counts) / len(word_counts)) if word_counts else 0
        data['error_rate'] = error_count / max(len(visited), 1)

    return data


def _parse_homepage(soup, base_url, data):
    # Viewport
    if soup.find('meta', attrs={'name': 'viewport'}):
        data['has_viewport_meta'] = True
    # Canonical
    if soup.find('link', rel='canonical'):
        data['has_canonical'] = True
    # Social links
    social_domains = ['twitter.com', 'linkedin.com', 'facebook.com',
                      'instagram.com', 'youtube.com', 'x.com']
    for a in soup.find_all('a', href=True):
        href = a['href'].lower()
        if any(s in href for s in social_domains):
            data['has_social_links'] = True
            data['has_social_presence'] = True
            break
    # External authority links
    authority_domains = ['.gov', '.edu', 'wikipedia.org', 'pubmed.ncbi',
                         'reuters.com', 'bbc.com', 'nature.com']
    for a in soup.find_all('a', href=True):
        href = a['href']
        if base_url not in href and any(d in href for d in authority_domains):
            data['has_external_authority_links'] = True
            break


def _parse_page(soup, url, base_url, data):
    url_lower = url.lower()

    # Page type detection
    if any(x in url_lower for x in ['/about', '/about-us', '/who-we-are']):
        data['has_about_page'] = True
    if any(x in url_lower for x in ['/contact', '/contact-us', '/get-in-touch']):
        data['has_contact_page'] = True
    if any(x in url_lower for x in ['/privacy', '/privacy-policy']):
        data['has_privacy_policy'] = True
    if any(x in url_lower for x in ['/terms', '/terms-of-service', '/tos']):
        data['has_terms'] = True

    # Author bios
    text = soup.get_text().lower()
    if any(x in text for x in ['about the author', 'written by', 'author bio']):
        data['has_author_bios'] = True

    # FAQ sections
    if any(x in text for x in ['frequently asked questions', 'faq', 'common questions']):
        data['has_faq_sections'] = True

    # Heading hierarchy
    h1s = soup.find_all('h1')
    h2s = soup.find_all('h2')
    if len(h1s) == 1 and len(h2s) >= 2:
        data['has_proper_headings'] = True

    # Visible dates
    time_tag = soup.find('time')
    if time_tag or any(x in text for x in ['published', 'updated', 'last modified']):
        data['has_visible_dates'] = True
        data['days_since_last_update'] = 30  # estimate

    # Direct answer format: first paragraph < 100 words
    first_p = soup.find('p')
    if first_p:
        words = first_p.get_text().split()
        if 20 <= len(words) <= 80:
            data['has_direct_answer_format'] = True


def _extract_internal_links(soup, base_url):
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('/'):
            href = base_url + href
        if base_url in href and href not in links:
            links.append(href)
    return links
```

---

## 8. Schema Detector

### `crawler/schema_detector.py`

```python
import json
from bs4 import BeautifulSoup


def detect_schema_types(html: str) -> dict:
    """
    Returns:
    {
        'types_detected': ['Organization', 'FAQPage', ...],
        'schemas_raw': [...]   # raw JSON-LD objects
    }
    """
    soup = BeautifulSoup(html, 'lxml')
    types_detected = set()
    schemas_raw = []

    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            # Handle array of schemas
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and '@graph' in data:
                items = data['@graph']
            else:
                items = [data]

            for item in items:
                schema_type = item.get('@type', '')
                if isinstance(schema_type, list):
                    for t in schema_type:
                        types_detected.add(t)
                else:
                    types_detected.add(schema_type)
                schemas_raw.append(item)
        except (json.JSONDecodeError, AttributeError):
            continue

    return {
        'types_detected': list(types_detected),
        'schemas_raw': schemas_raw
    }
```

---

## 9. Citation Checker

### `citation_checker/engine.py`

```python
"""
Queries AI engines with business-relevant questions and checks
if the target website URL appears in the response.
"""
import httpx
from openai import AsyncOpenAI
from django.conf import settings


async def check_perplexity(query: str, target_domain: str) -> dict:
    """Query Perplexity API and check if target_domain is cited."""
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "sonar",
        "messages": [{"role": "user", "content": query}],
        "return_citations": True,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json=payload)
        data = resp.json()

    answer = data.get('choices', [{}])[0].get('message', {}).get('content', '')
    citations = data.get('citations', [])
    was_cited = any(target_domain in c for c in citations)

    return {
        'ai_engine': 'perplexity',
        'query_used': query,
        'was_cited': was_cited,
        'ai_response_snippet': answer[:500],
        'all_citations': citations,
    }


async def check_chatgpt(query: str, target_domain: str) -> dict:
    """Query ChatGPT with web search and check if target_domain is cited."""
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    response = await client.responses.create(
        model="gpt-4o-mini",
        tools=[{"type": "web_search_preview"}],
        input=query,
    )

    answer = ''.join(
        block.text for block in response.output
        if hasattr(block, 'text')
    )
    was_cited = target_domain in answer

    return {
        'ai_engine': 'chatgpt',
        'query_used': query,
        'was_cited': was_cited,
        'ai_response_snippet': answer[:500],
    }


async def check_google_ai_overview(query: str, target_domain: str) -> dict:
    """Query Serper.dev and check Google AI Overview / answer box."""
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": settings.SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {"q": query, "num": 10}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json=payload)
        data = resp.json()

    answer_box = data.get('answerBox', {})
    knowledge_graph = data.get('knowledgeGraph', {})
    organic = data.get('organic', [])

    ai_text = (
        answer_box.get('answer', '') +
        answer_box.get('snippet', '') +
        knowledge_graph.get('description', '')
    )
    was_cited_in_answer = target_domain in ai_text
    was_cited_organic = any(target_domain in r.get('link', '') for r in organic[:5])

    return {
        'ai_engine': 'google',
        'query_used': query,
        'was_cited': was_cited_in_answer or was_cited_organic,
        'was_cited_in_ai_answer': was_cited_in_answer,
        'was_cited_in_organic': was_cited_organic,
        'ai_response_snippet': ai_text[:500],
    }


def generate_queries_for_website(crawl_data: dict, domain: str) -> list[str]:
    """
    Auto-generate 3-5 queries to test based on page titles and meta descriptions.
    Fallback to generic brand queries.
    """
    queries = []
    titles = crawl_data.get('page_titles', [])
    for title in titles[:3]:
        if title:
            queries.append(f"What is {title}?")
            queries.append(f"Best {title.lower()}")
    queries.append(f"About {domain}")
    queries.append(f"{domain} reviews")
    return list(dict.fromkeys(queries))[:5]  # deduplicate, max 5
```

---

## 10. Celery Tasks

### `config/celery.py`

```python
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
app = Celery('aivisibility')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

### `audits/tasks.py`

```python
import asyncio
from datetime import datetime, timezone

from celery import shared_task
from django.utils import timezone as dj_timezone

from .models import AuditReport, AuditFinding, CitationCheck
from crawler.engine import crawl_website
from crawler.schema_detector import detect_schema_types
from scorer.engine import (
    score_technical, score_schema, score_eeat,
    score_content, score_authority, calculate_overall_score
)
from citation_checker.engine import (
    check_perplexity, check_chatgpt, check_google_ai_overview,
    generate_queries_for_website
)
import httpx


@shared_task(bind=True, max_retries=2)
def run_audit(self, audit_id: str):
    """Main audit task. Orchestrates crawl → score → citation check."""
    from .models import AuditReport

    try:
        audit = AuditReport.objects.get(id=audit_id)
        audit.status = AuditReport.STATUS_RUNNING
        audit.started_at = dj_timezone.now()
        audit.save()

        url = audit.website.url
        domain = audit.website.domain

        # ── Step 1: Crawl ────────────────────────────────────────────────────
        crawl_data = asyncio.run(crawl_website(url))

        # ── Step 2: Detect schema ────────────────────────────────────────────
        homepage_html = _fetch_html(url)
        schema_data = detect_schema_types(homepage_html)

        # ── Step 3: Score each dimension ─────────────────────────────────────
        results = {
            'technical': score_technical(crawl_data),
            'schema':    score_schema(schema_data),
            'eeat':      score_eeat(crawl_data),
            'content':   score_content(crawl_data),
            'authority': score_authority(crawl_data),
        }

        dimension_scores = {k: v['score'] for k, v in results.items()}
        overall, grade = calculate_overall_score(dimension_scores)

        # ── Step 4: Save scores & findings ───────────────────────────────────
        audit.score_technical = dimension_scores['technical']
        audit.score_schema    = dimension_scores['schema']
        audit.score_eeat      = dimension_scores['eeat']
        audit.score_content   = dimension_scores['content']
        audit.score_authority = dimension_scores['authority']
        audit.overall_score   = overall
        audit.score_grade     = grade
        audit.crawl_data      = crawl_data
        audit.schema_data     = schema_data

        AuditFinding.objects.filter(audit=audit).delete()
        for dimension, result in results.items():
            for f in result['findings']:
                AuditFinding.objects.create(
                    audit=audit,
                    dimension=dimension,
                    severity=f['severity'],
                    title=f['title'],
                    description=f['description'],
                    recommendation=f['recommendation'],
                    points_impact=f['points_impact'],
                    is_passed=f['is_passed'],
                )

        # ── Step 5: Citation checks ───────────────────────────────────────────
        queries = generate_queries_for_website(crawl_data, domain)
        citation_results = asyncio.run(_run_citation_checks(queries, domain))

        for result in citation_results:
            CitationCheck.objects.create(
                audit=audit,
                ai_engine=result['ai_engine'],
                query_used=result['query_used'],
                was_cited=result['was_cited'],
                ai_response_snippet=result.get('ai_response_snippet', ''),
            )

        # ── Step 6: Complete ──────────────────────────────────────────────────
        audit.status = AuditReport.STATUS_COMPLETE
        audit.completed_at = dj_timezone.now()
        audit.save()

        # Update user's audit counter
        audit.website.user.audits_used_this_month += 1
        audit.website.user.save()

    except Exception as exc:
        audit.status = AuditReport.STATUS_FAILED
        audit.error_message = str(exc)
        audit.save()
        raise self.retry(exc=exc, countdown=60)


async def _run_citation_checks(queries, domain):
    results = []
    for query in queries[:3]:  # limit to 3 queries per audit
        try:
            r = await check_google_ai_overview(query, domain)
            results.append(r)
        except Exception:
            pass
        try:
            r = await check_perplexity(query, domain)
            results.append(r)
        except Exception:
            pass
    return results


def _fetch_html(url):
    try:
        with httpx.Client(timeout=10, follow_redirects=True) as c:
            return c.get(url).text
    except Exception:
        return ''
```

---

## 11. Django Views

### `audits/views.py`

```python
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from urllib.parse import urlparse

from .models import Website, AuditReport, AuditFinding
from .forms import AuditForm
from .tasks import run_audit


@login_required
def dashboard(request):
    websites = Website.objects.filter(user=request.user).prefetch_related('audits')
    context = {
        'websites': websites,
        'recent_audits': AuditReport.objects.filter(
            website__user=request.user,
            status=AuditReport.STATUS_COMPLETE
        ).order_by('-created_at')[:10],
    }
    return render(request, 'dashboard/index.html', context)


@login_required
def start_audit(request):
    if request.method == 'POST':
        form = AuditForm(request.POST)
        if form.is_valid():
            if not request.user.can_run_audit():
                messages.error(request, 'Monthly audit limit reached. Upgrade your plan.')
                return redirect('dashboard')

            url = form.cleaned_data['url']
            domain = urlparse(url).netloc.replace('www.', '')

            website, _ = Website.objects.get_or_create(
                user=request.user,
                domain=domain,
                defaults={'url': url, 'name': domain}
            )

            audit = AuditReport.objects.create(
                website=website,
                status=AuditReport.STATUS_PENDING,
            )

            run_audit.delay(str(audit.id))

            return redirect('audit_status', audit_id=audit.id)
    else:
        form = AuditForm()
    return render(request, 'audits/start.html', {'form': form})


@login_required
def audit_status(request, audit_id):
    audit = get_object_or_404(AuditReport, id=audit_id, website__user=request.user)
    return render(request, 'audits/status.html', {'audit': audit})


@login_required
def audit_status_poll(request, audit_id):
    """HTMX polling endpoint — returns JSON with status and redirect URL."""
    audit = get_object_or_404(AuditReport, id=audit_id, website__user=request.user)
    return JsonResponse({
        'status': audit.status,
        'redirect_url': reverse('audit_report', args=[audit_id])
        if audit.status == AuditReport.STATUS_COMPLETE else None,
    })


@login_required
def audit_report(request, audit_id):
    audit = get_object_or_404(
        AuditReport.objects.prefetch_related('findings', 'citation_checks'),
        id=audit_id, website__user=request.user
    )

    findings_by_dimension = {}
    for finding in audit.findings.all():
        findings_by_dimension.setdefault(finding.dimension, []).append(finding)

    citation_summary = {
        'total_checked': audit.citation_checks.count(),
        'times_cited': audit.citation_checks.filter(was_cited=True).count(),
    }

    context = {
        'audit': audit,
        'findings_by_dimension': findings_by_dimension,
        'citation_summary': citation_summary,
        'critical_fixes': audit.findings.filter(
            severity='critical', is_passed=False
        ).order_by('points_impact')[:5],
    }
    return render(request, 'audits/report.html', context)


@login_required
def audit_report_pdf(request, audit_id):
    """Generate downloadable PDF report."""
    from reports.generator import generate_pdf
    audit = get_object_or_404(AuditReport, id=audit_id, website__user=request.user)
    pdf_bytes = generate_pdf(audit)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="audit-{audit_id}.pdf"'
    return response
```

### `audits/urls.py`

```python
from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('audit/new/', views.start_audit, name='start_audit'),
    path('audit/<uuid:audit_id>/status/', views.audit_status, name='audit_status'),
    path('audit/<uuid:audit_id>/poll/', views.audit_status_poll, name='audit_status_poll'),
    path('audit/<uuid:audit_id>/report/', views.audit_report, name='audit_report'),
    path('audit/<uuid:audit_id>/pdf/', views.audit_report_pdf, name='audit_report_pdf'),
]
```

---

## 12. Forms

### `audits/forms.py`

```python
from django import forms
import re

class AuditForm(forms.Form):
    url = forms.URLField(
        label='Website URL',
        widget=forms.URLInput(attrs={
            'placeholder': 'https://yourwebsite.com',
            'class': 'w-full border rounded px-4 py-3 text-lg',
        }),
        help_text='Enter the full URL including https://'
    )

    def clean_url(self):
        url = self.cleaned_data['url']
        if not url.startswith(('http://', 'https://')):
            raise forms.ValidationError('Please enter a valid URL starting with https://')
        return url
```

---

## 13. Templates (Key Screens)

### `templates/base.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}AI Visibility Audit{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>
</head>
<body class="bg-gray-50 min-h-screen">
    <nav class="bg-white border-b px-6 py-4 flex justify-between items-center">
        <a href="{% url 'dashboard' %}" class="text-xl font-bold text-indigo-600">
            AI Visibility
        </a>
        {% if user.is_authenticated %}
        <div class="flex gap-4 items-center">
            <a href="{% url 'start_audit' %}"
               class="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium">
                New Audit
            </a>
            <a href="{% url 'account_logout' %}" class="text-gray-500 text-sm">Logout</a>
        </div>
        {% endif %}
    </nav>
    <main class="max-w-5xl mx-auto px-4 py-8">
        {% block content %}{% endblock %}
    </main>
</body>
</html>
```

### `templates/audits/status.html`

```html
{% extends 'base.html' %}
{% block content %}
<div class="text-center py-16">
    <div id="status-container">
        {% if audit.status == 'complete' %}
            <script>window.location = "{% url 'audit_report' audit.id %}";</script>
        {% elif audit.status == 'failed' %}
            <p class="text-red-600">Audit failed: {{ audit.error_message }}</p>
        {% else %}
            <div class="animate-spin w-16 h-16 border-4 border-indigo-600 border-t-transparent
                        rounded-full mx-auto mb-6"></div>
            <h2 class="text-2xl font-semibold mb-2">Auditing your website...</h2>
            <p class="text-gray-500">Crawling pages, checking schemas, testing AI citations.</p>
            <p class="text-gray-400 text-sm mt-2">This takes about 30–60 seconds.</p>
            <div
                hx-get="{% url 'audit_status_poll' audit.id %}"
                hx-trigger="every 3s"
                hx-swap="none"
                hx-on::after-request="
                    const d = JSON.parse(event.detail.xhr.response);
                    if (d.redirect_url) window.location = d.redirect_url;
                ">
            </div>
        {% endif %}
    </div>
</div>
{% endblock %}
```

### `templates/audits/report.html` (outline — expand as needed)

```html
{% extends 'base.html' %}
{% block content %}

{# Header score card #}
<div class="bg-white rounded-2xl shadow p-8 mb-8 flex items-center gap-8">
    <div class="text-center">
        <div class="text-7xl font-black
            {% if audit.score_grade == 'A' %}text-green-500
            {% elif audit.score_grade == 'B' %}text-blue-500
            {% elif audit.score_grade == 'C' %}text-yellow-500
            {% else %}text-red-500{% endif %}">
            {{ audit.score_grade }}
        </div>
        <div class="text-3xl font-bold text-gray-700">{{ audit.overall_score }}/100</div>
        <div class="text-gray-400 text-sm mt-1">AI Citability Score</div>
    </div>
    <div class="flex-1">
        <h1 class="text-2xl font-bold mb-1">{{ audit.website.domain }}</h1>
        <p class="text-gray-500 mb-4">Audited {{ audit.completed_at|date:"N j, Y" }}</p>
        <div class="grid grid-cols-5 gap-2 text-center text-sm">
            {% for dim, score in audit.get_dimension_scores.items %}
            <div class="bg-gray-50 rounded-lg p-2">
                <div class="font-bold text-lg">{{ score|floatformat:0 }}</div>
                <div class="text-gray-400 capitalize">{{ dim }}</div>
            </div>
            {% endfor %}
        </div>
    </div>
</div>

{# AI Citation Results #}
<div class="bg-white rounded-2xl shadow p-6 mb-6">
    <h2 class="text-xl font-bold mb-4">🤖 AI Citation Results</h2>
    <p class="text-gray-500 mb-4">
        We queried Google AI, Perplexity, and ChatGPT with questions related to your site.
        You were cited in
        <strong>{{ citation_summary.times_cited }}</strong> of
        <strong>{{ citation_summary.total_checked }}</strong> queries.
    </p>
    {% for check in audit.citation_checks.all %}
    <div class="border rounded-lg p-4 mb-3
        {% if check.was_cited %}border-green-200 bg-green-50{% else %}border-gray-200{% endif %}">
        <div class="flex justify-between items-start">
            <div>
                <span class="text-xs font-medium uppercase text-gray-400">{{ check.ai_engine }}</span>
                <p class="font-medium mt-1">{{ check.query_used }}</p>
            </div>
            {% if check.was_cited %}
                <span class="bg-green-100 text-green-700 text-xs font-bold px-3 py-1 rounded-full">
                    ✓ CITED
                </span>
            {% else %}
                <span class="bg-red-100 text-red-700 text-xs font-bold px-3 py-1 rounded-full">
                    ✗ NOT CITED
                </span>
            {% endif %}
        </div>
    </div>
    {% endfor %}
</div>

{# Critical Fixes #}
<div class="bg-red-50 border border-red-200 rounded-2xl p-6 mb-6">
    <h2 class="text-xl font-bold text-red-700 mb-4">🚨 Top Priority Fixes</h2>
    {% for finding in critical_fixes %}
    <div class="bg-white rounded-lg p-4 mb-3 border border-red-100">
        <div class="flex justify-between items-start mb-2">
            <h3 class="font-semibold">{{ finding.title }}</h3>
            <span class="text-red-500 font-bold text-sm">{{ finding.points_impact|floatformat:0 }} pts</span>
        </div>
        <p class="text-gray-600 text-sm mb-2">{{ finding.description }}</p>
        <p class="text-indigo-700 text-sm font-medium">✅ Fix: {{ finding.recommendation }}</p>
    </div>
    {% endfor %}
</div>

{# Findings by dimension #}
{% for dimension, findings in findings_by_dimension.items %}
<div class="bg-white rounded-2xl shadow p-6 mb-4">
    <h2 class="text-lg font-bold mb-4 capitalize">{{ dimension }} Analysis</h2>
    {% for f in findings %}
    <div class="flex items-start gap-3 py-3 border-b last:border-0">
        <span class="mt-0.5 text-xl">{% if f.is_passed %}✅{% else %}❌{% endif %}</span>
        <div>
            <p class="font-medium text-sm">{{ f.title }}</p>
            <p class="text-gray-500 text-sm">{{ f.description }}</p>
            {% if not f.is_passed %}
            <p class="text-indigo-600 text-sm mt-1">→ {{ f.recommendation }}</p>
            {% endif %}
        </div>
        <span class="ml-auto text-sm font-bold
            {% if f.points_impact > 0 %}text-green-600{% else %}text-red-500{% endif %}">
            {{ f.points_impact|floatformat:0 }}
        </span>
    </div>
    {% endfor %}
</div>
{% endfor %}

{# Download PDF #}
<div class="text-center mt-8">
    <a href="{% url 'audit_report_pdf' audit.id %}"
       class="bg-indigo-600 text-white px-6 py-3 rounded-lg font-medium inline-block">
        Download PDF Report
    </a>
</div>

{% endblock %}
```

---

## 14. Requirements

```txt
# requirements.txt
Django==5.1
djangorestframework==3.15
psycopg2-binary==2.9
redis==5.0
celery==5.4
httpx==0.27
beautifulsoup4==4.12
lxml==5.2
playwright==1.44
openai==1.30
python-decouple==3.8
django-allauth==0.63
WeasyPrint==62.3
Pillow==10.3
django-celery-beat==2.6
```

---

## 15. Environment Variables

```ini
# .env.example
SECRET_KEY=your-django-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://user:password@localhost:5432/aivisibility
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Third-party APIs
OPENAI_API_KEY=sk-...
PERPLEXITY_API_KEY=pplx-...
SERPER_API_KEY=...
```

---

## 16. Docker Compose

```yaml
# docker-compose.yml
version: "3.9"
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: aivisibility
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine

  web:
    build: .
    command: python manage.py runserver 0.0.0.0:8000
    ports: ["8000:8000"]
    volumes: [".:/app"]
    env_file: .env
    depends_on: [db, redis]

  celery:
    build: .
    command: celery -A config worker -l info
    volumes: [".:/app"]
    env_file: .env
    depends_on: [db, redis]

  celery-beat:
    build: .
    command: celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    volumes: [".:/app"]
    env_file: .env
    depends_on: [db, redis]

volumes:
  pgdata:
```

---

## 17. Build Order for Coding Agent

Give the agent this order to avoid dependency issues:

```
1. Django project scaffold: django-admin startproject config .
2. Create all apps: python manage.py startapp accounts audits crawler scorer citation_checker recommendations reports monitoring
3. config/settings/base.py — add all installed apps, database, celery, auth settings
4. accounts/models.py — custom User model (do this BEFORE first migration)
5. python manage.py makemigrations && migrate
6. audits/models.py — Website, AuditReport, AuditFinding, CitationCheck, MonitoringAlert
7. audits/forms.py
8. crawler/engine.py + crawler/schema_detector.py
9. scorer/engine.py — all 5 dimension scorers
10. citation_checker/engine.py
11. audits/tasks.py — Celery task
12. audits/views.py + audits/urls.py
13. config/urls.py — wire in audits.urls and allauth.urls
14. templates/ — base.html, dashboard, status, report
15. docker-compose.yml + Dockerfile
16. python manage.py createsuperuser — test locally
17. Run: docker-compose up
```

---

## 18. MVP vs. Future Roadmap

### MVP (Build First)
- [x] User auth (django-allauth)
- [x] Submit URL → crawl → score → report
- [x] 5-dimension scoring with findings
- [x] AI citation check (Perplexity + Google)
- [x] Report page with fixes
- [x] PDF download

### v2
- [ ] Competitor comparison (audit competitor URL, compare scores)
- [ ] Custom query input ("test my site for this specific question")
- [ ] Weekly email digest
- [ ] Monitoring mode (auto re-audit + alert on score change)

### v3
- [ ] White-label reports (for agencies)
- [ ] Team/agency accounts with multiple websites
- [ ] Stripe billing integration
- [ ] Public API

---

*End of specification.*
```
