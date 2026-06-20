from django.template.loader import render_to_string

from apps.audits.views import _report_context


def generate_pdf(audit, request=None):
    from weasyprint import HTML

    context = _report_context(audit)
    html = render_to_string("reports/audit_pdf.html", context=context, request=request)
    base_url = request.build_absolute_uri("/") if request else None
    return HTML(string=html, base_url=base_url).write_pdf()
