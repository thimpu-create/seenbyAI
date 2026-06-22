import asyncio

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.audits.models import AuditFinding, AuditReport, CitationCheck
from apps.citation_checker.engine import run_citation_checks
from apps.citation_checker.authority import enrich_authority_signals
from apps.crawler.engine import crawl_website, fetch_html
from apps.crawler.schema_detector import detect_schema_types
from apps.scorer.engine import (
    calculate_overall_score,
    score_authority,
    score_content,
    score_eeat,
    score_schema,
    score_technical,
)


@shared_task(bind=True)
def run_audit(self, audit_id: str):
    audit = AuditReport.objects.select_related("visitor").get(id=audit_id)
    try:
        audit.mark_running()
        crawl_data = asyncio.run(crawl_website(audit.url))
        crawl_data = asyncio.run(enrich_authority_signals(crawl_data, audit.domain))
        homepage_html = asyncio.run(fetch_html(audit.url))
        schema_data = detect_schema_types(homepage_html)
        crawl_data["schema_types_detected"] = schema_data.get("types_detected", [])

        results = {
            "technical": score_technical(crawl_data),
            "schema": score_schema(schema_data),
            "eeat": score_eeat(crawl_data),
            "content": score_content(crawl_data),
            "authority": score_authority(crawl_data),
        }
        dimension_scores = {key: value["score"] for key, value in results.items()}
        overall_score, grade = calculate_overall_score(dimension_scores)

        citation_results = asyncio.run(run_citation_checks(crawl_data, audit.domain))

        with transaction.atomic():
            audit.score_technical = dimension_scores["technical"]
            audit.score_schema = dimension_scores["schema"]
            audit.score_eeat = dimension_scores["eeat"]
            audit.score_content = dimension_scores["content"]
            audit.score_authority = dimension_scores["authority"]
            audit.overall_score = overall_score
            audit.score_grade = grade
            audit.crawl_data = crawl_data
            audit.schema_data = schema_data
            audit.citation_data = {"queries_checked": len(citation_results)}
            audit.status = AuditReport.STATUS_COMPLETE
            audit.completed_at = timezone.now()
            audit.save()

            AuditFinding.objects.filter(audit=audit).delete()
            for dimension, result in results.items():
                AuditFinding.objects.bulk_create(
                    [
                        AuditFinding(
                            audit=audit,
                            dimension=dimension,
                            severity=finding["severity"],
                            title=finding["title"],
                            description=finding["description"],
                            recommendation=finding["recommendation"],
                            points_impact=finding["points_impact"],
                            is_passed=finding["is_passed"],
                        )
                        for finding in result["findings"]
                    ]
                )

            CitationCheck.objects.filter(audit=audit).delete()
            CitationCheck.objects.bulk_create(
                [
                    CitationCheck(
                        audit=audit,
                        ai_engine=result["ai_engine"],
                        query_used=result["query_used"],
                        status=result.get("status", CitationCheck.STATUS_COMPLETE),
                        was_cited=result.get("was_cited", False),
                        citation_url=result.get("citation_url", ""),
                        ai_response_snippet=result.get("ai_response_snippet", ""),
                        all_citations=result.get("all_citations", []),
                    )
                    for result in citation_results
                ]
            )
    except Exception as exc:
        audit.status = AuditReport.STATUS_FAILED
        audit.error_message = str(exc)
        audit.completed_at = timezone.now()
        audit.save(update_fields=["status", "error_message", "completed_at"])
        _refund_failed_audit(audit)
        raise


def _refund_failed_audit(audit):
    if audit.credit_refunded:
        return
    if audit.customer_id:
        audit.customer.refund_audit_credit(audit.credit_type)
    else:
        audit.visitor.refund_audit_credit(audit.credit_type)
    audit.credit_refunded = True
    audit.save(update_fields=["credit_refunded"])
