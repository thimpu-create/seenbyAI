from collections import OrderedDict
from urllib.parse import urlparse

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.citation_checker.engine import build_readiness_display_snippet

from .forms import AuditForm
from .models import AuditReport, Customer, Visitor
from .tasks import run_audit


def landing(request):
    return render(request, "landing.html")

def about(request):
    return render(request, "about.html")

def privacy_policy(request):
    return render(request, "privacy_policy.html")

def terms_of_service(request):
    return render(request, "terms_of_service.html")

@login_required
def dashboard(request):
    visitor = request.visitor
    active_customer = _customer_for_user(request.user)
    _remember_customer_on_visitor(visitor, active_customer)
    recent_audits = _recent_audits(visitor, active_customer)
    context = {
        "form": AuditForm(),
        "recent_audits": recent_audits,
        "customer": active_customer,
        "quota_blocked": active_customer.total_audits_remaining <= 0 if active_customer else False,
    }
    return render(request, "audits/dashboard.html", context)


@login_required
def start_audit(request):
    if request.method != "POST":
        return redirect("dashboard")

    form = AuditForm(request.POST)
    active_customer = _customer_for_user(request.user)
    _remember_customer_on_visitor(request.visitor, active_customer)
    recent_audits = _recent_audits(request.visitor, active_customer)
    if not form.is_valid():
        return render(
            request,
            "audits/dashboard.html",
            {
                "form": form,
                "recent_audits": recent_audits,
                "customer": active_customer,
                "quota_blocked": active_customer.total_audits_remaining <= 0 if active_customer else False,
            },
        )

    with transaction.atomic():
        visitor = Visitor.objects.select_for_update().get(pk=request.visitor.pk)
        customer = Customer.objects.select_for_update().get(pk=active_customer.pk)
        visitor.email = customer.email
        visitor.save(update_fields=["email", "last_seen_at"])

        credit_type = customer.reserve_audit_credit()
        if credit_type is None:
            messages.warning(request, "This email has used its 2 free scans. Buy credits to continue.")
            return redirect("checkout")

        url = form.cleaned_data["url"]
        domain = urlparse(url).netloc.lower().replace("www.", "")
        audit = AuditReport.objects.create(
            visitor=visitor,
            customer=customer,
            url=url,
            domain=domain,
            credit_type=credit_type,
        )

    run_audit.delay(str(audit.id))
    return redirect("audit_status", audit_id=audit.id)


@login_required
def audit_status(request, audit_id):
    audit = get_object_or_404(_visible_audits(request).filter(id=audit_id))
    return render(request, "audits/status.html", {"audit": audit})


@login_required
def audit_status_poll(request, audit_id):
    audit = get_object_or_404(_visible_audits(request).filter(id=audit_id))
    return JsonResponse(
        {
            "status": audit.status,
            "redirect_url": reverse("audit_report", args=[audit.id])
            if audit.status == AuditReport.STATUS_COMPLETE
            else None,
            "error_message": audit.error_message if audit.status == AuditReport.STATUS_FAILED else "",
        }
    )


@login_required
def audit_report(request, audit_id):
    audit = get_object_or_404(
        _visible_audits(request).prefetch_related("findings", "citation_checks").filter(id=audit_id),
    )
    context = _report_context(audit)
    return render(request, "audits/report.html", context)


@login_required
def audit_report_pdf(request, audit_id):
    from apps.reports.generator import generate_pdf

    audit = get_object_or_404(
        _visible_audits(request).prefetch_related("findings", "citation_checks").filter(id=audit_id),
    )
    pdf_bytes = generate_pdf(audit, request=request)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="seenbyai-{audit.domain}-{audit.id}.pdf"'
    return response


def _report_context(audit):
    findings_by_dimension = OrderedDict((key, []) for key in ["technical", "schema", "eeat", "content", "authority"])
    for finding in audit.findings.all():
        findings_by_dimension.setdefault(finding.dimension, []).append(finding)

    citation_checks = audit.citation_checks.all()
    live_checks = [check for check in citation_checks if check.is_live_evidence]
    simulation_checks = [check for check in citation_checks if check.is_simulation]
    crawl_context = dict(audit.crawl_data or {})
    crawl_context.setdefault("schema_types_detected", (audit.schema_data or {}).get("types_detected", []))
    for check in live_checks:
        check.display_snippet = check.ai_response_snippet
    for check in simulation_checks:
        if check.status == "complete":
            check.display_snippet = build_readiness_display_snippet(
                crawl_context,
                audit.domain,
                raw_reasoning=check.ai_response_snippet,
                is_likely_ready=check.was_cited,
            )
        else:
            check.display_snippet = check.ai_response_snippet
    completed_live_checks = [check for check in live_checks if check.status == "complete"]
    completed_simulation_checks = [check for check in simulation_checks if check.status == "complete"]
    citation_summary = {
        "total_checked": len(completed_live_checks),
        "times_cited": sum(1 for check in completed_live_checks if check.was_cited),
        "skipped": sum(1 for check in live_checks if check.status == "skipped"),
        "failed": sum(1 for check in live_checks if check.status == "failed"),
    }
    simulation_summary = {
        "total_checked": len(completed_simulation_checks),
        "likely_ready": sum(1 for check in completed_simulation_checks if check.was_cited),
        "skipped": sum(1 for check in simulation_checks if check.status == "skipped"),
        "failed": sum(1 for check in simulation_checks if check.status == "failed"),
    }
    simulation_result = _simulation_result(audit, crawl_context, simulation_checks, simulation_summary)

    critical_fixes = audit.findings.filter(is_passed=False).exclude(severity="pass").order_by("points_impact")[:6]
    return {
        "audit": audit,
        "findings_by_dimension": findings_by_dimension,
        "dimension_scores": audit.get_dimension_scores(),
        "citation_summary": citation_summary,
        "simulation_summary": simulation_summary,
        "simulation_result": simulation_result,
        "live_citation_checks": live_checks,
        "simulation_checks": simulation_checks,
        "critical_fixes": critical_fixes,
    }


def _simulation_result(audit, crawl_context, simulation_checks, simulation_summary):
    prompts = list(dict.fromkeys(check.query_used for check in simulation_checks if check.query_used))
    total_checked = simulation_summary["total_checked"]
    likely_ready = simulation_summary["likely_ready"]
    has_checks = bool(simulation_checks)

    if total_checked == 0:
        status_label = "Not available"
        is_likely_ready = False
        display_snippet = (
            simulation_checks[0].display_snippet
            if simulation_checks
            else "No AI-readiness simulation was stored for this scan."
        )
    else:
        is_likely_ready = likely_ready == total_checked
        status_label = "Likely ready" if is_likely_ready else "Needs work"
        display_snippet = build_readiness_display_snippet(
            crawl_context,
            audit.domain,
            raw_reasoning="",
            is_likely_ready=is_likely_ready,
        )

    return {
        "has_checks": has_checks,
        "prompts": prompts,
        "status_label": status_label,
        "is_likely_ready": is_likely_ready,
        "display_snippet": display_snippet,
    }


def _customer_for_user(user):
    email = Customer.normalize_email(user.email)
    customer, _ = Customer.objects.get_or_create(email=email)
    return customer


def _remember_customer_on_visitor(visitor, customer):
    if visitor.email != customer.email:
        visitor.email = customer.email
        visitor.save(update_fields=["email", "last_seen_at"])


def _recent_audits(visitor, customer):
    if customer:
        return AuditReport.objects.filter(customer=customer).order_by("-created_at")[:8]
    return AuditReport.objects.filter(visitor=visitor).order_by("-created_at")[:8]


def _visible_audits(request):
    visitor = request.visitor
    customer = _customer_for_user(request.user)
    _remember_customer_on_visitor(visitor, customer)
    query = Q(visitor=visitor)
    if customer:
        query |= Q(customer=customer)
    return AuditReport.objects.filter(query).distinct()
