from django.contrib import admin

from .models import AuditFinding, AuditReport, CitationCheck, Customer, Visitor


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("email", "free_audits_used", "paid_audit_credits", "updated_at")
    search_fields = ("email",)


@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "free_audits_used", "paid_audit_credits", "last_seen_at")
    search_fields = ("id", "email", "ip_hash")


class AuditFindingInline(admin.TabularInline):
    model = AuditFinding
    extra = 0
    readonly_fields = ("dimension", "severity", "title", "points_impact", "is_passed")


class CitationCheckInline(admin.TabularInline):
    model = CitationCheck
    extra = 0
    readonly_fields = ("ai_engine", "query_used", "status", "was_cited", "citation_url")


@admin.register(AuditReport)
class AuditReportAdmin(admin.ModelAdmin):
    list_display = ("domain", "customer", "status", "overall_score", "score_grade", "credit_type", "created_at")
    list_filter = ("status", "credit_type", "score_grade")
    search_fields = ("domain", "url", "visitor__email", "customer__email")
    inlines = [AuditFindingInline, CitationCheckInline]


@admin.register(AuditFinding)
class FindingAdmin(admin.ModelAdmin):
    list_display = ("title", "dimension", "severity", "points_impact", "is_passed")
    list_filter = ("dimension", "severity", "is_passed")


@admin.register(CitationCheck)
class CitationCheckAdmin(admin.ModelAdmin):
    list_display = ("ai_engine", "status", "was_cited", "citation_url", "checked_at")
    list_filter = ("ai_engine", "status", "was_cited")
