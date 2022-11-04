import logging
from datetime import timedelta

from django.utils import timezone
from freezegun import freeze_time

from websecmap.organizations.models import Organization, Url
from websecmap.reporting.models import ScanPolicy
from websecmap.scanners.models import (
    Activity,
    Endpoint,
    EndpointGenericScan,
    PlannedScan,
    PlannedScanStatistic,
    State,
    Scanner,
    FollowUpScan,
)
from websecmap.scanners.plannedscan import (
    calculate_progress,
    finish_multiple,
    get_latest_progress,
    pickup,
    request,
    reset,
    retrieve_endpoints_from_urls,
    store_progress,
    plan_follow_up_scans,
)
from websecmap.scanners.scanner.tls_qualys import plan_scan

log = logging.getLogger("websecmap")


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
    return egs


def test_plannedscan(db, default_scan_metadata):
    o = create_organization("Test")
    u1 = create_url("example.com")
    link_url_to_organization(u1, o)
    u2 = create_url("example2.com")
    link_url_to_organization(u2, o)

    scanner = Scanner.objects.all().get(python_name="tls_qualys")
    scanner_id = scanner.id

    request(scanner="tls_qualys", activity="scan", urls=[u1, u2])
    assert PlannedScan.objects.all().count() == 2
    assert PlannedScan.objects.all().filter(state=State["requested"].value).count() == 2
    assert calculate_progress() == [
        {
            "scanner": scanner_id,
            "activity": Activity["scan"].value,
            "state": State["requested"].value,
            "amount": 2,
        }
    ]

    urls = pickup(scanner="tls_qualys", activity="scan", amount=10)
    assert len(urls) == 2
    assert PlannedScan.objects.all().filter(state=State["picked_up"]).count() == 2
    assert calculate_progress() == [
        {
            "scanner": scanner_id,
            "activity": Activity["scan"].value,
            "state": State["picked_up"].value,
            "amount": 2,
        }
    ]

    # Verify that you cannot pickup more than the usual 500, in this max 498:
    # todo: get this from caplog: Picking up maximum 498 of total 498 free slots.
    pickup(scanner="tls_qualys", activity="scan", amount=1000)

    finish_multiple(scanner="tls_qualys", activity="scan", urls=[url.pk for url in urls])
    assert PlannedScan.objects.all().filter(state=State["finished"]).count() == 2

    # Finished means that the previous steps will be added to the list if they are not present yet.
    assert calculate_progress() == [
        {
            "activity": Activity["scan"].value,
            "amount": 0,
            "scanner": scanner_id,
            "state": State["requested"].value,
        },
        {
            "activity": Activity["scan"].value,
            "amount": 0,
            "scanner": scanner_id,
            "state": State["picked_up"].value,
        },
        {
            "scanner": scanner_id,
            "activity": Activity["scan"].value,
            "state": State["finished"].value,
            "amount": 2,
        },
    ]

    # test storage:
    store_progress()
    assert get_latest_progress() == calculate_progress()
    assert PlannedScanStatistic.objects.count() == 1
    old_progress = get_latest_progress()

    # test that a new call will store new data
    store_progress()
    assert PlannedScanStatistic.objects.count() == 2

    # make sure only the latest is retrieved:
    request(scanner="tls_qualys", activity="scan", urls=[u1, u2])
    store_progress()
    assert get_latest_progress() == calculate_progress()
    assert PlannedScanStatistic.objects.count() == 3
    assert old_progress != get_latest_progress()


def test_plan_scans(db, default_scan_metadata):
    scanner = Scanner.objects.all().get(python_name="tls_qualys")
    scanner_id = scanner.id

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
        assert calculate_progress() == [
            {
                "scanner": scanner_id,
                "activity": Activity["scan"].value,
                "state": State["requested"].value,
                "amount": 2,
            }
        ]

        # if there are already planned, no new scans will be created
        plan_scan()
        assert calculate_progress() == [
            {
                "scanner": scanner_id,
                "activity": Activity["scan"].value,
                "state": State["requested"].value,
                "amount": 2,
            }
        ]

        # to test what happens on endpoints that already have scans:
        reset()

        # with very recent scans no new scans will be created:
        create_endpoint_scan(e1, "tls_qualys_encryption_quality", "F", timezone.now())
        create_endpoint_scan(e2, "tls_qualys_encryption_quality", "A", timezone.now())
        plan_scan()
        assert calculate_progress() == []

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
        assert PlannedScan.objects.all().filter(state=State["requested"].value).count() == 1
        assert calculate_progress() == [
            {
                "scanner": scanner_id,
                "activity": Activity["scan"].value,
                "state": State["requested"].value,
                "amount": 1,
            }
        ]

        EndpointGenericScan.objects.all().delete()

        # test
        # with very old scans both scans will be requested
        create_endpoint_scan(e1, "tls_qualys_encryption_quality", "F", timezone.now() - timedelta(days=6))
        create_endpoint_scan(e2, "tls_qualys_encryption_quality", "A", timezone.now() - timedelta(days=100))
        plan_scan()
        assert PlannedScan.objects.all().filter(state=State["requested"].value).count() == 2
        assert calculate_progress() == [
            {
                "scanner": scanner_id,
                "activity": Activity["scan"].value,
                "state": State["requested"].value,
                "amount": 2,
            }
        ]


def test_retrieve_endpoints_from_urls(db):
    u1 = Url.objects.create(url="example.com")
    u2 = Url.objects.create(url="example.nl")
    e1 = Endpoint.objects.create(url=u1, protocol="http", port="443")

    endpoints, urls_without_endpoints = retrieve_endpoints_from_urls([u1.id, u2.id], protocols=["http", "https"])

    assert endpoints == [e1]
    assert urls_without_endpoints == [u2.id]


def test_plan_follow_up_scan(db, default_scan_metadata, default_policy):
    """
    A follow up scan happens when one of the policies match with what is found.
    """
    now = timezone.now()
    yesterday = now - timedelta(days=1)

    # Eg: make a follow up scan with a simple policy:
    tls_scanner = Scanner.objects.all().filter(python_name="tls_qualys").first()
    policy = ScanPolicy.objects.all().filter(scan_type="tls_qualys_encryption_quality", conclusion="F").first()
    follow = FollowUpScan.objects.create(follow_up_scanner=tls_scanner)
    follow.run_follow_up_on_any_of_these_policies.add(policy)

    # prepare an endpoint:
    u1 = Url.objects.create(url="example.nl")
    e1 = Endpoint.objects.create(url=u1, protocol="http", port="443")

    # Some things that does not match the policy
    EndpointGenericScan.objects.create(
        endpoint=e1,
        rating="G",
        type="tls_qualys_encryption_quality",
        last_scan_moment=now,
        rating_determined_on=yesterday,
    )
    EndpointGenericScan.objects.create(
        endpoint=e1,
        rating="False",
        type="tls_qualys_certificate_trusted",
        last_scan_moment=now,
        rating_determined_on=yesterday,
    )
    # or are too old:
    EndpointGenericScan.objects.create(
        endpoint=e1,
        rating="A",
        type="tls_qualys_encryption_quality",
        last_scan_moment=yesterday,
        rating_determined_on=yesterday,
    )

    # This should not deliver any new scan request:
    plan_follow_up_scans()
    assert PlannedScan.objects.all().count() == 0

    # Something that matches the policy and is accurate:
    EndpointGenericScan.objects.create(
        endpoint=e1,
        rating="F",
        type="tls_qualys_encryption_quality",
        last_scan_moment=now,
        rating_determined_on=yesterday,
    )
    EndpointGenericScan.objects.create(
        endpoint=e1,
        rating="F",
        type="tls_qualys_encryption_quality",
        last_scan_moment=now,
        rating_determined_on=yesterday,
    )
    EndpointGenericScan.objects.create(
        endpoint=e1,
        rating="F",
        type="tls_qualys_encryption_quality",
        last_scan_moment=now,
        rating_determined_on=yesterday,
    )
    plan_follow_up_scans()
    plan_follow_up_scans()
    plan_follow_up_scans()
    assert PlannedScan.objects.all().count() == 1
