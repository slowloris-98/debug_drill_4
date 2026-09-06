"""Waypoint domain models.

Waypoint sits between a hiring platform and the applicant tracking systems its
customers run. Grading partners deliver score reports over the public API, the
customer's recruiters release those reports, and Waypoint pushes the released
results into the customer's ATS — over webhooks when the ATS accepts them, and
over an incremental sync feed the customer's connector polls.
"""

from django.contrib.auth.models import User
from django.db import models


class Organization(models.Model):
    """A paying customer account. Every other row in the system hangs off one."""

    ATS_PROVIDERS = [
        ("greenhouse", "Greenhouse"),
        ("lever", "Lever"),
        ("workday", "Workday"),
    ]

    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    ats_provider = models.CharField(max_length=20, choices=ATS_PROVIDERS)
    owner = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="organization"
    )
    created_at = models.DateTimeField()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ApiKey(models.Model):
    """Credential for the public API. Sent as `Authorization: Api-Key <key>`."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="api_keys"
    )
    key = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=80)
    created_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["organization__name", "created_at"]

    @property
    def is_active(self):
        return self.revoked_at is None

    def __str__(self):
        return f"{self.organization.name} / {self.label}"


class Assessment(models.Model):
    """One test a customer sends candidates through.

    `pass_mark` is the score at or above which a candidate reaches the customer's
    shortlist. It is expressed on the same scale as `max_score`.
    """

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="assessments"
    )
    name = models.CharField(max_length=140)
    max_score = models.IntegerField(default=100)
    pass_mark = models.IntegerField(default=60)
    created_at = models.DateTimeField()

    class Meta:
        ordering = ["organization__name", "name"]

    def __str__(self):
        return f"{self.organization.name} — {self.name}"


class Candidate(models.Model):
    """A person sitting one of the customer's assessments."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="candidates"
    )
    external_ref = models.CharField(max_length=64)
    full_name = models.CharField(max_length=120)
    email = models.EmailField()
    created_at = models.DateTimeField()

    class Meta:
        ordering = ["full_name"]
        unique_together = [("organization", "external_ref")]

    def __str__(self):
        return self.full_name


class ScoreReport(models.Model):
    """One graded result, as delivered by a grading partner.

    A report is `graded` once the partner has delivered it and `published` once
    the customer has released it to their ATS. `raw_score` is stored exactly as
    the partner sent it.
    """

    PENDING = "pending"
    GRADED = "graded"
    PUBLISHED = "published"
    VOID = "void"

    STATUSES = [
        (PENDING, "Pending"),
        (GRADED, "Graded"),
        (PUBLISHED, "Published"),
        (VOID, "Void"),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="score_reports"
    )
    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="score_reports"
    )
    candidate = models.ForeignKey(
        Candidate, on_delete=models.CASCADE, related_name="score_reports"
    )
    raw_score = models.CharField(max_length=8)
    status = models.CharField(max_length=20, choices=STATUSES, default=PENDING)
    partner_ref = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField()
    graded_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["updated_at", "id"]

    def __str__(self):
        return f"{self.candidate.full_name} — {self.assessment.name}"


class WebhookEndpoint(models.Model):
    """Where a customer's ATS connector receives events.

    `events` is the list of event types this endpoint is subscribed to. An
    endpoint is only sent events it names.
    """

    RESULT_PUBLISHED = "result.published"
    RESULT_UPDATED = "result.updated"
    CANDIDATE_CREATED = "candidate.created"

    EVENT_TYPES = [RESULT_PUBLISHED, RESULT_UPDATED, CANDIDATE_CREATED]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="webhook_endpoints"
    )
    url = models.URLField()
    secret = models.CharField(max_length=64)
    events = models.JSONField(default=list)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField()

    class Meta:
        ordering = ["organization__name", "id"]

    def __str__(self):
        return self.url


class WebhookDelivery(models.Model):
    """One queued or attempted push to a customer's endpoint."""

    endpoint = models.ForeignKey(
        WebhookEndpoint, on_delete=models.CASCADE, related_name="deliveries"
    )
    report = models.ForeignKey(
        ScoreReport, on_delete=models.CASCADE, related_name="deliveries", null=True, blank=True
    )
    event_type = models.CharField(max_length=40)
    status_code = models.IntegerField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at", "-id"]
        unique_together = [("endpoint", "report", "event_type")]

    def __str__(self):
        return f"{self.event_type} -> {self.endpoint.url}"
