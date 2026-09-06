"""Releasing graded reports, one at a time and in bulk."""

from django.utils import timezone

from core.models import ScoreReport, WebhookDelivery, WebhookEndpoint
from core.services import publish_report, publish_reports


def graded(organization, count):
    return list(
        ScoreReport.objects.filter(
            organization=organization, status=ScoreReport.GRADED
        )[:count]
    )


def deliveries_for(report):
    return WebhookDelivery.objects.filter(
        report=report, event_type=WebhookEndpoint.RESULT_PUBLISHED
    )


def test_single_publish_queues_a_webhook(northgate):
    report = graded(northgate, 1)[0]

    publish_report(report)

    assert report.status == ScoreReport.PUBLISHED
    assert deliveries_for(report).count() == 1


def test_publishing_a_published_report_does_not_duplicate_the_webhook(northgate):
    report = graded(northgate, 1)[0]

    publish_report(report)
    publish_report(report)

    assert deliveries_for(report).count() == 1


def test_bulk_publish_advances_updated_at(northgate):
    reports = graded(northgate, 3)
    before = timezone.now()

    published = publish_reports([report.id for report in reports])

    assert published == 3
    for report in reports:
        report.refresh_from_db()
        assert report.status == ScoreReport.PUBLISHED
        assert report.updated_at >= before


def test_bulk_publish_queues_one_webhook_per_report(northgate):
    reports = graded(northgate, 3)

    publish_reports([report.id for report in reports])

    for report in reports:
        assert deliveries_for(report).count() == 1
