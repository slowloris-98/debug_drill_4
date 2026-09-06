"""Shortlisting.

A shortlist is the candidates on one assessment whose score reached the
assessment's pass mark, best first. Recruiters work top-down through it and the
customer's ATS receives it in that order.
"""

from core.models import ScoreReport

CONSIDERED_STATUSES = (ScoreReport.GRADED, ScoreReport.PUBLISHED)


def considered_reports(assessment):
    """Every report on this assessment that a recruiter is entitled to see."""
    return (
        ScoreReport.objects.filter(
            assessment=assessment, status__in=CONSIDERED_STATUSES
        )
        .select_related("candidate")
    )


def shortlist(assessment):
    """Candidates on `assessment` who reached its pass mark, best first."""
    qualified = considered_reports(assessment).filter(
        raw_score__gte=assessment.pass_mark
    )

    return [
        {
            "candidate_ref": report.candidate.external_ref,
            "candidate_name": report.candidate.full_name,
            "score": report.raw_score,
        }
        for report in qualified.order_by("-raw_score", "candidate__full_name")
    ]
