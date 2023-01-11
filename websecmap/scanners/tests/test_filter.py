import pytest
from django.utils import timezone

from websecmap.map.models import Configuration
from websecmap.organizations.models import Url, Organization, OrganizationType
from websecmap.scanners.models import PlannedScan, Endpoint
from websecmap.scanners.scanner.dnssec import plan_scan as dnssec_plan_scan
from websecmap.scanners.scanner.ftp import plan_scan as ftp_plan_scan
from websecmap.scanners.scanner.http import plan_discover as http_plan_discover
from websecmap.scanners.scanner.http import plan_verify as http_plan_verify
from websecmap.scanners.scanner.plain_http import plan_scan as plain_http_plan_scan


@pytest.fixture()
def setup_some_data():
    ot = OrganizationType.objects.create(name="test")
    Configuration.objects.create(country="NL", organization_type=ot, is_scanned=True)

    organization = Organization.objects.create(name="test", type=ot, created_on=timezone.now(), country="NL")
    organization.layers.add(ot)
    url = Url.objects.create(url="google.com")
    url.organization.add(organization)

    Endpoint.objects.create(url=url, discovered_on=timezone.now(), port=80, protocol="http", ip_version=4)


def yeet():
    PlannedScan.objects.all().delete()


def test_filter_top_level_domains_with_organization(db, default_scan_metadata, setup_some_data):
    dnssec_plan_scan(organizations_filter={"name": "asdasd"})
    assert PlannedScan.objects.count() == 0

    dnssec_plan_scan(organizations_filter={"name": "test"})
    assert PlannedScan.objects.count() == 1
    yeet()


def test_filter_top_level_domains_with_url(db, default_scan_metadata, setup_some_data):
    dnssec_plan_scan()
    assert PlannedScan.objects.count() == 1
    yeet()

    dnssec_plan_scan(urls_filter={"url": "test.nl"})
    assert PlannedScan.objects.count() == 0

    dnssec_plan_scan(urls_filter={"url": "google.com"})
    assert PlannedScan.objects.count() == 1
    yeet()

    dnssec_plan_scan(urls_filter={"computed_domain": "google"})
    assert PlannedScan.objects.count() == 1
    yeet()

    dnssec_plan_scan(urls_filter={"computed_suffix": "com"})
    assert PlannedScan.objects.count() == 1
    yeet()


def test_filter_top_level_domains_with_endpoint(db, default_scan_metadata, setup_some_data):
    # Test filtering on endpoint
    # three misses
    dnssec_plan_scan(endpoints_filter={"protocol": "https"})
    assert PlannedScan.objects.count() == 0
    dnssec_plan_scan(endpoints_filter={"port": 90})
    assert PlannedScan.objects.count() == 0
    dnssec_plan_scan(endpoints_filter={"ip_version": 6})
    assert PlannedScan.objects.count() == 0

    # three hits
    dnssec_plan_scan(endpoints_filter={"protocol": "http"})
    assert PlannedScan.objects.count() == 1
    yeet()
    dnssec_plan_scan(endpoints_filter={"port": 80})
    assert PlannedScan.objects.count() == 1
    yeet()
    dnssec_plan_scan(endpoints_filter={"ip_version": 4})
    assert PlannedScan.objects.count() == 1
    yeet()


def test_filter_ftp_plan_scan_endpoints(db, default_scan_metadata, setup_some_data):
    ftp_plan_scan()
    assert PlannedScan.objects.count() == 0

    Endpoint.objects.create(
        url=Url.objects.all().first(), discovered_on=timezone.now(), port=21, protocol="ftp", ip_version=4
    )
    ftp_plan_scan()
    assert PlannedScan.objects.count() == 1
    yeet()


def test_filter_http(db, default_scan_metadata, setup_some_data):

    # see if nothing happens when there is no endpoint
    Endpoint.objects.all().delete()
    http_plan_verify()
    assert PlannedScan.objects.count() == 0

    # one url, so one discovery task:
    http_plan_discover()
    assert PlannedScan.objects.count() == 1
    yeet()

    # add an enpoint that can be verified:
    Endpoint.objects.create(
        url=Url.objects.all().first(), discovered_on=timezone.now(), port=80, protocol="http", ip_version=4
    )
    http_plan_verify()
    assert PlannedScan.objects.count() == 1
    yeet()


def test_filter_plain_http(db, default_scan_metadata, setup_some_data):
    Endpoint.objects.all().delete()
    plain_http_plan_scan()
    assert PlannedScan.objects.count() == 0

    Endpoint.objects.create(
        url=Url.objects.all().first(), discovered_on=timezone.now(), port=80, protocol="http", ip_version=4
    )
    plain_http_plan_scan()
    assert PlannedScan.objects.count() == 1
    yeet()

    plain_http_plan_scan(organizations_filter={"name": "not_existing"})
    assert PlannedScan.objects.count() == 0

    plain_http_plan_scan(organizations_filter={"name": "test"})
    assert PlannedScan.objects.count() == 1
