from django.contrib import admin

from core.models import (
    ApiKey,
    Assessment,
    Candidate,
    Organization,
    ScoreReport,
    WebhookDelivery,
    WebhookEndpoint,
)


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "ats_provider", "created_at")


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("organization", "label", "key", "revoked_at")


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "max_score", "pass_mark")


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("full_name", "organization", "external_ref", "email")
    search_fields = ("full_name", "email", "external_ref")


@admin.register(ScoreReport)
class ScoreReportAdmin(admin.ModelAdmin):
    list_display = ("candidate", "assessment", "raw_score", "status", "updated_at")
    list_filter = ("status", "assessment")


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ("organization", "url", "active")


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ("endpoint", "event_type", "status_code", "attempts", "created_at")
