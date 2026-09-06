"""Shortlisting a graded cohort."""

from core.models import ScoreReport
from reporting.shortlist import shortlist

TOP_FIVE = [
    "Nadia Farouk",
    "Marcus Okonjo",
    "Elena Petrova",
    "Samuel Adeyemi",
    "Priti Ranganathan",
]


def names(entries):
    return [entry["candidate_name"] for entry in entries]


def test_shortlist_is_ranked_by_numeric_score(screen):
    assert names(shortlist(screen))[:5] == TOP_FIVE


def test_the_cutoff_admits_exactly_the_scores_at_or_above_it(screen):
    shortlisted = names(shortlist(screen))

    assert len(shortlisted) == 17
    assert "Nadia Farouk" in shortlisted
    assert "Colin Radcliffe" not in shortlisted
    assert "Ahmed Chaudhry" in shortlisted
    assert "Rosa Villanueva" not in shortlisted


def test_every_shortlisted_score_is_a_number_above_the_pass_mark(screen):
    scores = [entry["score"] for entry in shortlist(screen)]

    assert scores
    assert all(str(score).isdigit() for score in scores)
    assert all(int(score) >= screen.pass_mark for score in scores)


def test_the_shortlist_only_contains_reports_from_this_assessment(screen):
    shortlisted = {entry["candidate_ref"] for entry in shortlist(screen)}

    cohort = set(
        ScoreReport.objects.filter(assessment=screen).values_list(
            "candidate__external_ref", flat=True
        )
    )
    assert shortlisted
    assert shortlisted <= cohort
