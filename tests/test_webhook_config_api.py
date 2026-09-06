"""Changing a webhook endpoint through the public API."""

from tests.conftest import NORTHGATE_KEY, VOLTA_KEY, auth

NEW_URL = "https://ingest.volta-automotive.example/v2/waypoint"


def endpoint_of(organization):
    return organization.webhook_endpoints.get()


def test_patching_the_url_changes_it(api_client, volta):
    endpoint = endpoint_of(volta)

    response = api_client.patch(
        f"/api/v1/webhooks/{endpoint.id}/",
        {"url": NEW_URL},
        format="json",
        **auth(VOLTA_KEY),
    )

    assert response.status_code == 200
    endpoint.refresh_from_db()
    assert endpoint.url == NEW_URL


def test_patching_events_changes_them(api_client, volta):
    endpoint = endpoint_of(volta)

    response = api_client.patch(
        f"/api/v1/webhooks/{endpoint.id}/",
        {"events": ["result.published"]},
        format="json",
        **auth(VOLTA_KEY),
    )

    assert response.status_code == 200
    endpoint.refresh_from_db()
    assert endpoint.events == ["result.published"]
    assert response.json()["events"] == ["result.published"]


def test_a_payload_we_cannot_apply_is_rejected(api_client, volta):
    endpoint = endpoint_of(volta)
    original_url = endpoint.url

    response = api_client.patch(
        f"/api/v1/webhooks/{endpoint.id}/",
        {"target_url": NEW_URL},
        format="json",
        **auth(VOLTA_KEY),
    )

    assert response.status_code == 400
    endpoint.refresh_from_db()
    assert endpoint.url == original_url


def test_another_customers_endpoint_is_not_reachable(api_client, volta):
    endpoint = endpoint_of(volta)

    response = api_client.patch(
        f"/api/v1/webhooks/{endpoint.id}/",
        {"active": False},
        format="json",
        **auth(NORTHGATE_KEY),
    )

    assert response.status_code == 404
    endpoint.refresh_from_db()
    assert endpoint.active is True
