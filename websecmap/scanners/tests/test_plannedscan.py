import logging
from datetime import timedelta

from django.utils import timezone
from freezegun import freeze_time

from websecmap.organizations.models import Organization, Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan, PlannedScan
from websecmap.scanners.plannedscan import finish_multiple, pickup, progress, request, reset
from websecmap.scanners.scanner.tls_qualys import plan_scan

log = logging.getLogger('websecmap')


def create_organization(name="Test"):
    o = Organization()
    o.name = name
    o.save()
    return o


def create_url(url: str = "example.com"):
    u = Url()
    u.url = url
    u.not_resolvable = False
    u.is_dead = False
    u.save()
    return u


def link_url_to_organization(url: Url, organization: Organization):
    url.organization.add(organization)
    url.save()
    return url


def create_endpoint(url, ip_version, protocol, port):
    e = Endpoint()
    e.url = url
    e.ip_version = ip_version
    e.protocol = protocol
    e.port = port
    e.is_dead = False
    e.save()
    return e


def create_endpoint_scan(endpoint, type, rating, at_when):
    egs = EndpointGenericScan()
    egs.endpoint = endpoint
    egs.is_the_latest_scan = True
    egs.rating = rating
    egs.last_scan_moment = at_when
    egs.rating_determined_on = at_when
    egs.type = type
    egs.save()

    # overwrite the auto_now_add behavior (todo: remove this implicit behavior)
    egs.last_scan_moment = at_when
    egs.save()


def test_plannedscan(db):

    o = create_organization("Test")
    u1 = create_url("example.com")
    link_url_to_organization(u1, o)
    u2 = create_url("example2.com")
    link_url_to_organization(u2, o)

    request(scanner="tls_qualys", activity="scan", urls=[u1, u2])
    assert PlannedScan.objects.all().count() == 2
    assert PlannedScan.objects.all().filter(state="requested").count() == 2
    assert progress() == [{'scanner': 'tls_qualys', 'activity': 'scan', 'state': 'requested', 'amount': 2}]

    urls = pickup(scanner="tls_qualys", activity="scan", amount=10)
    assert len(urls) == 2
    assert PlannedScan.objects.all().filter(state="picked_up").count() == 2
    assert progress() == [{'scanner': 'tls_qualys', 'activity': 'scan', 'state': 'picked_up', 'amount': 2}]

    finish_multiple(scanner="tls_qualys", activity="scan", urls=urls)
    assert PlannedScan.objects.all().filter(state="finished").count() == 2

    assert progress() == [{'scanner': 'tls_qualys', 'activity': 'scan', 'state': 'finished', 'amount': 2}]


def test_plan_scans(db):

    with freeze_time("2020-01-01"):

        o = create_organization("Test")
        u1 = create_url("example.com")
        e1 = create_endpoint(u1, 4, "https", 443)
        link_url_to_organization(u1, o)
        u2 = create_url("example2.com")
        e2 = create_endpoint(u2, 4, "https", 443)
        link_url_to_organization(u2, o)

        # plan scans on endpoints that have never been scanned.
        plan_scan()
        assert progress() == [{'scanner': 'tls_qualys', 'activity': 'scan', 'state': 'requested', 'amount': 2}]

        # if there are already planned, no new scans will be created
        plan_scan()
        assert progress() == [{'scanner': 'tls_qualys', 'activity': 'scan', 'state': 'requested', 'amount': 2}]

        # to test what happens on endpoints that already have scans:
        reset()

        # with very recent scans no new scans will be created:
        create_endpoint_scan(e1, "tls_qualys_encryption_quality", "F", timezone.now())
        create_endpoint_scan(e2, "tls_qualys_encryption_quality", "A", timezone.now())
        plan_scan()
        assert progress() == []

        # this does not delete endpoints...
        EndpointGenericScan.objects.all().delete()

        # test
        # with some older data, the scan for the bad endpoint will be requested
        create_endpoint_scan(e1, "tls_qualys_encryption_quality", "F", timezone.now() - timedelta(days=100))
        create_endpoint_scan(e2, "tls_qualys_encryption_quality", "A", timezone.now())

        # make sure the endpoint is created:
        first_egs = EndpointGenericScan.objects.last()
        assert first_egs.endpoint == e1
        assert EndpointGenericScan.objects.all().count() == 2
        egs = EndpointGenericScan.objects.all().filter(rating="F").first()
        assert egs.rating_determined_on < timezone.now() - timedelta(days=4)
        assert egs.last_scan_moment < timezone.now() - timedelta(days=4)
        assert egs.is_the_latest_scan is True

        plan_scan()
        assert PlannedScan.objects.all().filter(state="requested").count() == 1
        assert progress() == [{'scanner': 'tls_qualys', 'activity': 'scan', 'state': 'requested', 'amount': 1}]

        EndpointGenericScan.objects.all().delete()

        # test
        # with very old scans both scans will be requested
        create_endpoint_scan(e1, "tls_qualys_encryption_quality", "F", timezone.now() - timedelta(days=6))
        create_endpoint_scan(e2, "tls_qualys_encryption_quality", "A", timezone.now() - timedelta(days=100))
        plan_scan()
        assert PlannedScan.objects.all().filter(state="requested").count() == 2
        assert progress() == [{'scanner': 'tls_qualys', 'activity': 'scan', 'state': 'requested', 'amount': 2}]
