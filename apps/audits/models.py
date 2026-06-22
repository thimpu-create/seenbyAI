import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class CustomerManager(models.Manager):
    def for_email(self, email):
        normalized = self.model.normalize_email(email)
        return self.get_or_create(email=normalized)


class Customer(models.Model):
    email = models.EmailField(unique=True)
    free_audits_used = models.PositiveSmallIntegerField(default=0)
    paid_audit_credits = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomerManager()

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return self.email

    @staticmethod
    def normalize_email(email):
        return (email or "").strip().lower()

    @property
    def free_audits_remaining(self):
        return max(settings.FREE_AUDIT_LIMIT - self.free_audits_used, 0)

    @property
    def total_audits_remaining(self):
        return self.free_audits_remaining + self.paid_audit_credits

    def reserve_audit_credit(self):
        if self.free_audits_used < settings.FREE_AUDIT_LIMIT:
            self.free_audits_used += 1
            self.save(update_fields=["free_audits_used", "updated_at"])
            return AuditReport.CREDIT_FREE
        if self.paid_audit_credits > 0:
            self.paid_audit_credits -= 1
            self.save(update_fields=["paid_audit_credits", "updated_at"])
            return AuditReport.CREDIT_PAID
        return None

    def refund_audit_credit(self, credit_type):
        if credit_type == AuditReport.CREDIT_FREE and self.free_audits_used > 0:
            self.free_audits_used -= 1
        elif credit_type == AuditReport.CREDIT_PAID:
            self.paid_audit_credits += 1
        self.save(update_fields=["free_audits_used", "paid_audit_credits", "updated_at"])


class Visitor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cookie_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    ip_hash = models.CharField(max_length=64, blank=True)
    user_agent_hash = models.CharField(max_length=64, blank=True)
    email = models.EmailField(blank=True)
    free_audits_used = models.PositiveSmallIntegerField(default=0)
    paid_audit_credits = models.PositiveIntegerField(default=0)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self):
        return str(self.id)

    @property
    def free_audits_remaining(self):
        return max(settings.FREE_AUDIT_LIMIT - self.free_audits_used, 0)

    @property
    def total_audits_remaining(self):
        return self.free_audits_remaining + self.paid_audit_credits

    def reserve_audit_credit(self):
        if self.free_audits_used < settings.FREE_AUDIT_LIMIT:
            self.free_audits_used += 1
            self.save(update_fields=["free_audits_used", "last_seen_at"])
            return AuditReport.CREDIT_FREE
        if self.paid_audit_credits > 0:
            self.paid_audit_credits -= 1
            self.save(update_fields=["paid_audit_credits", "last_seen_at"])
            return AuditReport.CREDIT_PAID
        return None

    def refund_audit_credit(self, credit_type):
        if credit_type == AuditReport.CREDIT_FREE and self.free_audits_used > 0:
            self.free_audits_used -= 1
        elif credit_type == AuditReport.CREDIT_PAID:
            self.paid_audit_credits += 1
        self.save(update_fields=["free_audits_used", "paid_audit_credits", "last_seen_at"])


class AuditReport(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETE = "complete"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETE, "Complete"),
        (STATUS_FAILED, "Failed"),
    ]

    CREDIT_FREE = "free"
    CREDIT_PAID = "paid"
    CREDIT_CHOICES = [
        (CREDIT_FREE, "Free"),
        (CREDIT_PAID, "Paid"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name="audits")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="audits", null=True, blank=True)
    url = models.URLField(max_length=500)
    domain = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    credit_type = models.CharField(max_length=20, choices=CREDIT_CHOICES, default=CREDIT_FREE)
    credit_refunded = models.BooleanField(default=False)

    overall_score = models.FloatField(null=True, blank=True)
    score_grade = models.CharField(max_length=2, blank=True)
    score_technical = models.FloatField(null=True, blank=True)
    score_schema = models.FloatField(null=True, blank=True)
    score_eeat = models.FloatField(null=True, blank=True)
    score_content = models.FloatField(null=True, blank=True)
    score_authority = models.FloatField(null=True, blank=True)

    crawl_data = models.JSONField(default=dict)
    schema_data = models.JSONField(default=dict)
    citation_data = models.JSONField(default=dict)
    technical_data = models.JSONField(default=dict)

    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["visitor", "-created_at"]),
            models.Index(fields=["domain"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.domain} ({self.status})"

    def mark_running(self):
        self.status = self.STATUS_RUNNING
        self.started_at = timezone.now()
        self.save(update_fields=["status", "started_at"])

    def get_dimension_scores(self):
        return {
            "technical": self.score_technical or 0,
            "schema": self.score_schema or 0,
            "eeat": self.score_eeat or 0,
            "content": self.score_content or 0,
            "authority": self.score_authority or 0,
        }


class AuditFinding(models.Model):
    SEVERITY_CRITICAL = "critical"
    SEVERITY_HIGH = "high"
    SEVERITY_MEDIUM = "medium"
    SEVERITY_LOW = "low"
    SEVERITY_PASS = "pass"
    SEVERITY_CHOICES = [
        (SEVERITY_CRITICAL, "Critical"),
        (SEVERITY_HIGH, "High"),
        (SEVERITY_MEDIUM, "Medium"),
        (SEVERITY_LOW, "Low"),
        (SEVERITY_PASS, "Pass"),
    ]

    audit = models.ForeignKey(AuditReport, on_delete=models.CASCADE, related_name="findings")
    dimension = models.CharField(max_length=30)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    title = models.CharField(max_length=255)
    description = models.TextField()
    recommendation = models.TextField(blank=True)
    points_impact = models.FloatField(default=0)
    is_passed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["dimension", "is_passed", "points_impact"]

    def __str__(self):
        return self.title


class CitationCheck(models.Model):
    ENGINE_LABELS = {
        "brave_search": "Brave Search",
        "brave_llm_context": "Brave AI Context",
        "ollama_local": "Local AI Readiness Check",
        "llm_citation": "AI Readiness Check",
        "citation_provider": "Citation Provider",
    }
    SIMULATION_ENGINES = {"ollama_local", "llm_citation"}
    LIVE_EVIDENCE_ENGINES = {"brave_search", "brave_llm_context"}

    STATUS_COMPLETE = "complete"
    STATUS_SKIPPED = "skipped"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_COMPLETE, "Complete"),
        (STATUS_SKIPPED, "Skipped"),
        (STATUS_FAILED, "Failed"),
    ]

    audit = models.ForeignKey(AuditReport, on_delete=models.CASCADE, related_name="citation_checks")
    ai_engine = models.CharField(max_length=50)
    query_used = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_COMPLETE)
    was_cited = models.BooleanField(default=False)
    citation_url = models.URLField(blank=True)
    ai_response_snippet = models.TextField(blank=True)
    all_citations = models.JSONField(default=list)
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["ai_engine", "query_used"]

    def __str__(self):
        return f"{self.ai_engine}: {self.query_used[:40]}"

    @property
    def engine_label(self):
        return self.ENGINE_LABELS.get(self.ai_engine, self.ai_engine.replace("_", " ").title())

    @property
    def is_simulation(self):
        return self.ai_engine in self.SIMULATION_ENGINES

    @property
    def is_live_evidence(self):
        return self.ai_engine in self.LIVE_EVIDENCE_ENGINES
