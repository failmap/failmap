"""Shared fixtures used by different tests."""
import pytest

from failmap_admin.organizations.models import Organization, Url
from failmap_admin.scanners.models import Endpoint


@pytest.fixture
def faalonië():
    """A testing organization complete with URL's and endpoints."""

    faalonië = Organization(name='faalonië')
    faalonië.save()

    url = Url(url='www.faalonie.test')
    url.save()
    url.organization.add(faalonië)

    endpoint = Endpoint(ip='127.0.0.1', protocol='https', url=url)
    endpoint.save()

    return {
        'organization': faalonië,
        'url': url,
        'endpoint': endpoint,
    }
