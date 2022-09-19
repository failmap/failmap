"""Shared fixtures used by different tests."""
import pytest
from django.core.management import call_command

from websecmap.organizations.models import Organization, Url
from websecmap.scanners.models import Endpoint


@pytest.fixture
def faaloniae():
    """A testing organization complete with URL's and endpoints."""

    faaloniae = Organization(name="faalonië")
    faaloniae.save()

    url = Url(url="www.faalonie.test")
    url.save()
    url.organization.add(faaloniae)

    endpoint = Endpoint(ip_version=4, port=443, protocol="https", url=url)
    endpoint.save()

    return {
        "organization": faaloniae,
        "url": url,
        "endpoint": endpoint,
    }


# todo: move this up in the conftest levels, aka: higher directory does not warrent redefines??
@pytest.fixture
def default_scan_metadata():
    # Using this construct to avoid using the django test classes which indent everything 4 spaces for no added value
    call_command("loaddata", "scanmetadata", verbosity=0)


@pytest.fixture
def default_policy():
    # Using this construct to avoid using the django test classes which indent everything 4 spaces for no added value
    call_command("loaddata", "default_policy", verbosity=0)
