"""Shared fixtures.

The whole suite runs against the demo dataset built by `manage.py seed_demo`,
loaded once into the test database. Each test runs in a transaction that is
rolled back afterwards, so tests may write freely without affecting each other.
"""

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from core.models import Organization

# Keys as issued to customers. See `core/management/commands/seed_demo.py`.
VOLTA_KEY = "wp_live_volta_3d81f4a9c2"
NORTHGATE_KEY = "wp_live_northgate_6b27ce80d4"
LAKESHORE_KEY = "wp_live_lakeshore_9a54f1bb37"


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        call_command("seed_demo", verbosity=0)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def volta(db):
    return Organization.objects.get(slug="volta")


@pytest.fixture
def northgate(db):
    return Organization.objects.get(slug="northgate")


@pytest.fixture
def lakeshore(db):
    return Organization.objects.get(slug="lakeshore")


@pytest.fixture
def screen(lakeshore):
    """Lakeshore's June backend screen — the cohort in TICKET-6613."""
    return lakeshore.assessments.get(name__startswith="Backend Engineer")


def auth(key):
    """Header kwargs for an API-key request."""
    return {"HTTP_AUTHORIZATION": f"Api-Key {key}"}
