"""Public API views.

Every endpoint here is scoped to the organization that owns the credential on
the request.
"""

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics, status
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Assessment, Candidate, ScoreReport, WebhookEndpoint
from core.services import publish_report
from api.serializers import (
    ScoreReportIngestSerializer,
    ScoreReportSerializer,
    WebhookEndpointSerializer,
)
from reporting.pass_rates import pass_rates
from reporting.shortlist import shortlist


def resolve_organization(request):
    """The organization this request is acting as."""
    return request.auth.organization


class ScoreReportListView(generics.ListAPIView):
    """`GET /api/v1/results/` — the caller's score reports, oldest change first.

    `?updated_since=<iso8601>` returns only the reports that have changed since
    that instant. ATS connectors poll this with the timestamp of their last
    successful run.
    """

    serializer_class = ScoreReportSerializer

    def get_queryset(self):
        queryset = ScoreReport.objects.filter(
            organization=resolve_organization(self.request)
        ).select_related("candidate", "assessment")

        report_status = self.request.query_params.get("status")
        if report_status:
            queryset = queryset.filter(status=report_status)

        updated_since = self.request.query_params.get("updated_since")
        if updated_since:
            parsed = parse_datetime(updated_since)
            if parsed is None:
                raise ParseError("updated_since must be an ISO-8601 timestamp.")
            queryset = queryset.filter(updated_at__gt=parsed)

        return queryset.order_by("updated_at", "id")


class ScoreReportIngestView(APIView):
    """`POST /api/v1/results/` — a grading partner delivers one marked report."""

    def post(self, request):
        organization = resolve_organization(request)
        serializer = ScoreReportIngestSerializer(
            data=request.data, context={"organization": organization}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        assessment = get_object_or_404(
            Assessment, pk=data["assessment"], organization=organization
        )
        candidate = Candidate.objects.get(
            organization=organization, external_ref=data["candidate_ref"]
        )
        now = timezone.now()
        report, _ = ScoreReport.objects.update_or_create(
            partner_ref=data["partner_ref"],
            defaults={
                "organization": organization,
                "assessment": assessment,
                "candidate": candidate,
                "raw_score": data["raw_score"],
                "status": ScoreReport.GRADED,
                "created_at": now,
                "graded_at": now,
            },
        )
        return Response(
            ScoreReportSerializer(report).data, status=status.HTTP_201_CREATED
        )


class ScoreReportDetailView(APIView):
    """`PATCH /api/v1/results/<id>/` — release one report to the customer's ATS."""

    def get_object(self, request, pk):
        return get_object_or_404(
            ScoreReport, pk=pk, organization=resolve_organization(request)
        )

    def get(self, request, pk):
        return Response(ScoreReportSerializer(self.get_object(request, pk)).data)

    def patch(self, request, pk):
        report = self.get_object(request, pk)
        requested = request.data.get("status")
        if requested != ScoreReport.PUBLISHED:
            return Response(
                {"detail": "status must be 'published'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        publish_report(report)
        report.refresh_from_db()
        return Response(ScoreReportSerializer(report).data)


class WebhookEndpointListView(generics.ListAPIView):
    """`GET /api/v1/webhooks/` — the caller's endpoints."""

    serializer_class = WebhookEndpointSerializer
    pagination_class = None

    def get_queryset(self):
        return WebhookEndpoint.objects.filter(organization=resolve_organization(self.request))


class WebhookEndpointDetailView(generics.RetrieveUpdateAPIView):
    """`GET`/`PATCH /api/v1/webhooks/<id>/` — read or change one endpoint."""

    serializer_class = WebhookEndpointSerializer

    def get_queryset(self):
        return WebhookEndpoint.objects.filter(organization=resolve_organization(self.request))


class ShortlistView(APIView):
    """`GET /api/v1/shortlists/<assessment_id>/` — candidates at or above the pass mark."""

    def get(self, request, assessment_id):
        assessment = get_object_or_404(
            Assessment, pk=assessment_id, organization=resolve_organization(request)
        )
        return Response(
            {
                "assessment": assessment.name,
                "pass_mark": assessment.pass_mark,
                "candidates": shortlist(assessment),
            }
        )


class PassRateView(APIView):
    """`GET /api/v1/pass-rates/` — one summary row per assessment."""

    def get(self, request):
        organization = resolve_organization(request)
        return Response({"assessments": pass_rates(organization)})
