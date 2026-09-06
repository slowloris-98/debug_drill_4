"""Internal recruiting dashboard.

Signed-in customer staff see their own organization's assessments, releases and
webhook configuration.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from core.models import Assessment, Organization, ScoreReport, WebhookDelivery
from reporting.pass_rates import pass_rates
from reporting.shortlist import shortlist


def organization_for(user):
    organization = getattr(user, "organization", None)
    if organization is not None:
        return organization
    return Organization.objects.first()


@login_required
def shortlist_page(request):
    organization = organization_for(request.user)
    summaries = pass_rates(organization)

    selected_id = request.GET.get("assessment")
    if selected_id:
        assessment = get_object_or_404(
            Assessment, pk=selected_id, organization=organization
        )
    else:
        assessment = organization.assessments.first()

    return render(
        request,
        "dashboard/shortlist.html",
        {
            "organization": organization,
            "summaries": summaries,
            "assessment": assessment,
            "entries": shortlist(assessment) if assessment else [],
        },
    )


@login_required
def releases_page(request):
    organization = organization_for(request.user)
    reports = (
        ScoreReport.objects.filter(
            organization=organization, status=ScoreReport.PUBLISHED
        )
        .select_related("candidate", "assessment")
        .order_by("-published_at", "-id")[:60]
    )
    return render(
        request,
        "dashboard/releases.html",
        {"organization": organization, "reports": reports},
    )


@login_required
def webhooks_page(request):
    organization = organization_for(request.user)
    endpoints = organization.webhook_endpoints.all()
    deliveries = (
        WebhookDelivery.objects.filter(endpoint__organization=organization)
        .select_related("endpoint", "report__candidate")
        .order_by("-created_at", "-id")[:40]
    )
    return render(
        request,
        "dashboard/webhooks.html",
        {
            "organization": organization,
            "endpoints": endpoints,
            "deliveries": deliveries,
        },
    )
