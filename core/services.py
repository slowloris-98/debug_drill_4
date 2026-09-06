"""Write-side operations on score reports.

Recruiters release results either one at a time from a candidate's page or in
bulk from the assessment's release screen. Both routes end here.
"""

from django.db import transaction
from django.utils import timezone

from core.models import ScoreReport


def publish_report(report):
    """Release a single graded report to the customer's ATS."""
    if report.status != ScoreReport.GRADED:
        return report

    report.status = ScoreReport.PUBLISHED
    report.published_at = timezone.now()
    report.save()
    return report


@transaction.atomic
def publish_reports(report_ids):
    """Release a batch of graded reports to the customer's ATS.

    Returns the number of reports released.
    """
    return (
        ScoreReport.objects.filter(id__in=report_ids, status=ScoreReport.GRADED)
        .update(status=ScoreReport.PUBLISHED, published_at=timezone.now())
    )
