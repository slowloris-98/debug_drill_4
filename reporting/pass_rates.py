"""Per-assessment summary for the recruiting dashboard.

One row per assessment: how many reports came back, how many of those
candidates actually attempted the assessment, how many reached the pass mark,
and the cohort's average score.
"""

from django.db import connection

SUMMARY_SQL = """
    SELECT COUNT(*)                                             AS reports,
           SUM(CASE WHEN r.raw_score = '' THEN 1 ELSE 0 END)    AS not_attempted,
           SUM(CASE WHEN r.raw_score >= %s THEN 1 ELSE 0 END)   AS passed,
           AVG(r.raw_score)                                     AS average_score
      FROM core_scorereport r
     WHERE r.organization_id = %s
       AND r.assessment_id = %s
       AND r.status IN ('graded', 'published')
"""


def assessment_summary(assessment):
    """Reports, attempts, passes and average score for one assessment."""
    with connection.cursor() as cursor:
        cursor.execute(
            SUMMARY_SQL,
            [assessment.pass_mark, assessment.organization_id, assessment.id],
        )
        reports, not_attempted, passed, average_score = cursor.fetchone()

    reports = reports or 0
    not_attempted = not_attempted or 0
    passed = passed or 0
    attempted = reports - not_attempted

    return {
        "assessment_id": assessment.id,
        "assessment": assessment.name,
        "pass_mark": assessment.pass_mark,
        "reports": reports,
        "attempted": attempted,
        "not_attempted": not_attempted,
        "passed": passed,
        "pass_rate": round(passed / attempted, 4) if attempted else 0.0,
        "average_score": round(average_score, 2) if average_score is not None else None,
    }


def pass_rates(organization):
    """One summary row per assessment the organization runs."""
    return [
        assessment_summary(assessment)
        for assessment in organization.assessments.all()
    ]
