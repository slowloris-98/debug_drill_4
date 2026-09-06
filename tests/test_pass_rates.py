"""The per-assessment summary behind the dashboard."""

import pytest

from reporting.pass_rates import assessment_summary
from reporting.shortlist import shortlist


def test_every_delivered_report_is_counted(screen):
    assert assessment_summary(screen)["reports"] == 43


def test_the_summary_agrees_with_the_shortlist(screen):
    assert assessment_summary(screen)["passed"] == len(shortlist(screen))


def test_pass_count_uses_the_numeric_score(screen):
    row = assessment_summary(screen)

    assert row["attempted"] == 37
    assert row["passed"] == 17
    assert row["pass_rate"] == pytest.approx(0.4595, abs=0.0001)


def test_reports_with_no_numeric_score_are_not_counted_as_zero(screen):
    row = assessment_summary(screen)

    assert row["not_attempted"] == 6
    assert row["average_score"] == pytest.approx(53.27, abs=0.01)
