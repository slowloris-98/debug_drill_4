"""The incremental sync feed an ATS connector polls."""

import datetime as dt

from django.utils import timezone

from core.models import ScoreReport
from core.services import publish_reports
from tests.conftest import LAKESHORE_KEY, NORTHGATE_KEY, auth


def graded(organization, count):
    return list(
        ScoreReport.objects.filter(
            organization=organization, status=ScoreReport.GRADED
        )[:count]
    )


def test_a_request_without_a_key_is_rejected(api_client, northgate):
    response = api_client.get("/api/v1/results/")

    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers


def test_the_feed_only_contains_the_callers_reports(api_client, northgate, lakeshore):
    response = api_client.get(
        "/api/v1/results/", {"page_size": 500}, **auth(NORTHGATE_KEY)
    )

    assert response.status_code == 200
    returned = {row["id"] for row in response.json()["results"]}
    others = set(
        ScoreReport.objects.filter(organization=lakeshore).values_list("id", flat=True)
    )
    assert returned
    assert not returned & others


def test_updated_since_must_be_a_timestamp(api_client, northgate):
    response = api_client.get(
        "/api/v1/results/", {"updated_since": "last tuesday"}, **auth(NORTHGATE_KEY)
    )

    assert response.status_code == 400


def test_publishing_one_report_makes_it_visible_to_the_feed(api_client, lakeshore):
    report = graded(lakeshore, 1)[0]
    since = timezone.now() - dt.timedelta(seconds=1)

    response = api_client.patch(
        f"/api/v1/results/{report.id}/",
        {"status": "published"},
        format="json",
        **auth(LAKESHORE_KEY),
    )
    assert response.status_code == 200

    feed = api_client.get(
        "/api/v1/results/",
        {"updated_since": since.isoformat(), "page_size": 500},
        **auth(LAKESHORE_KEY),
    )
    assert report.id in {row["id"] for row in feed.json()["results"]}


def test_bulk_published_reports_appear_in_the_updated_since_feed(api_client, northgate):
    reports = graded(northgate, 5)
    since = timezone.now() - dt.timedelta(seconds=1)

    publish_reports([report.id for report in reports])

    feed = api_client.get(
        "/api/v1/results/",
        {"updated_since": since.isoformat(), "page_size": 500},
        **auth(NORTHGATE_KEY),
    )
    assert feed.status_code == 200
    returned = {row["id"] for row in feed.json()["results"]}
    assert {report.id for report in reports} <= returned
