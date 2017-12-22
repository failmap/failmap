"""Shared fixtures used by different tests."""
import pytest

from failmap.organizations.models import Organization, Url
from failmap.scanners.models import Endpoint


@pytest.fixture
def faalonië():
    """A testing organization complete with URL's and endpoints."""

    faalonië = Organization(name='faalonië')
    faalonië.save()

    url = Url(url='www.faalonie.test')
    url.save()
    url.organization.add(faalonië)

    endpoint = Endpoint(ip_version=4, port=443, protocol='https', url=url)
    endpoint.save()

    return {
        'organization': faalonië,
        'url': url,
        'endpoint': endpoint,
    }
