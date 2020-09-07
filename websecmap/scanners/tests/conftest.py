"""Shared fixtures used by different tests."""
import pytest

from websecmap.organizations.models import Organization, Url
from websecmap.scanners.models import Endpoint


@pytest.fixture
def faaloniae():
    """A testing organization complete with URL's and endpoints."""

    faaloniae = Organization(name='faalonië')
    faaloniae.save()

    url = Url(url='www.faalonie.test')
    url.save()
    url.organization.add(faaloniae)

    endpoint = Endpoint(ip_version=4, port=443, protocol='https', url=url)
    endpoint.save()

    return {
        'organization': faaloniae,
        'url': url,
        'endpoint': endpoint,
    }
