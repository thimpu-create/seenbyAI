from django.urls import path

from . import views


urlpatterns = [
    path("", views.landing, name="landing"),
    path("robots.txt", views.robots_txt, name="robots_txt"),
    path("sitemap.xml", views.sitemap_xml, name="sitemap_xml"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("about/", views.about, name="about"),
    path("privacy-policy/", views.privacy_policy, name="privacy_policy"),
    path("terms-of-service/", views.terms_of_service, name="terms_of_service"),
    path("audits/start/", views.start_audit, name="start_audit"),
    path("audits/<uuid:audit_id>/status/", views.audit_status, name="audit_status"),
    path("audits/<uuid:audit_id>/poll/", views.audit_status_poll, name="audit_status_poll"),
    path("audits/<uuid:audit_id>/", views.audit_report, name="audit_report"),
    path("audits/<uuid:audit_id>/pdf/", views.audit_report_pdf, name="audit_report_pdf"),
]
