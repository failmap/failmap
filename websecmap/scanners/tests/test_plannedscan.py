import logging
from datetime import datetime, timedelta, timezone

from freezegun import freeze_time
import json

from websecmap.organizations.models import Organization, Url
from websecmap.reporting.models import ScanPolicy
from websecmap.scanners.models import (
    Activity,
    Endpoint,
    EndpointGenericScan,
    FollowUpScan,
    PlannedScan,
    PlannedScanLog,
    PlannedScanStatistic,
    Scanner,
    State,
)
from websecmap.scanners.plannedscan import (
    calculate_progress,
    finish_multiple,
    get_latest_progress,
    pickup,
    plan_follow_up_scans,
    request,
    reset,
    retrieve_endpoints_from_urls,
    store_progress,
    set_scan_state,
    retry,
)
from websecmap.scanners.scanner.autoexplain_no_https_possible import scan
from websecmap.scanners.scanner.tls_qualys import plan_scan
from constance.test.pytest import override_config

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


def create_endpoint_scan(endpoint, type, rating, at_when, evidence="{}"):
    egs = EndpointGenericScan()
    egs.endpoint = endpoint
    egs.is_the_latest_scan = True
    egs.rating = rating
    egs.last_scan_moment = at_when
    egs.evidence = evidence
    egs.rating_determined_on = at_when
    egs.type = type
    egs.save()

    # overwrite the auto_now_add behavior (todo: remove this implicit behavior)
    egs.last_scan_moment = at_when
    egs.save()
    return egs


# during tests this doesn't work as we're working with a cached value, which will have previously
# been cached. So in this case we're setting the default in settings.py to true, below statement
# doesn't affect the cached value at all. It's still here because you, the next programmer, will add it :)
@override_config(SCANNER_LOG_PLANNED_SCANS=True)
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

    # See if there are loglines:
    loglines = PlannedScanLog.objects.all()
    assert len(loglines) == 10
    assert loglines[0].line == "Url: example.com, Activity: scan, Scanner: tls_qualys, State: requested, Origin: "


def test_plan_scans(db, default_scan_metadata, default_policy):
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

        # Obsolete, due to expensive queries: if there are already planned, no new scans will be created
        # When new stuff is requested it will be scanned! And all of these scans will progress simultaneously.
        plan_scan()
        assert calculate_progress() == [
            {
                "scanner": scanner_id,
                "activity": Activity["scan"].value,
                "state": State["requested"].value,
                "amount": 2 + 2,
            }
        ]

        # to test what happens on endpoints that already have scans:
        reset()
        plan_scan()
        assert calculate_progress() == [{"activity": 3, "amount": 2, "scanner": 22, "state": 1}]
        plan_scan()
        plan_scan()
        plan_scan()
        # repeating this planning while it still doesnt have scans...
        assert calculate_progress() == [{"activity": 3, "amount": 8, "scanner": 22, "state": 1}]

        # let's give them scans, so no new scans will be created
        # with matching scans.
        log.debug("Testing that adding new scans does not create new scans...")
        evidence = [
            {
                "subject": "CN=mijn-acc.groningen.nl",
                "commonNames": ["mijn-acc.groningen.nl"],
                "altNames": ["mijn-acc.groningen.nl"],
                "notBefore": 1702015407000,
                "notAfter": (datetime.now(timezone.utc) + timedelta(days=100)).timestamp(),
                "issuerSubject": "CN=R3, O=Let's Encrypt, C=US",
                "issuerLabel": "R3",
                "sigAlg": "SHA256withRSA",
                "revocationInfo": 2,
                "crlURIs": [""],
                "ocspURIs": ["http://r3.o.lencr.org"],
                "revocationStatus": 2,
                "crlRevocationStatus": 4,
                "ocspRevocationStatus": 2,
                "sgc": 0,
                "issues": 0,
                "sct": True,
                "mustStaple": 0,
                "sha1Hash": "c1f3b82b761a15945ab991ae4900bc10e65edbd8",
                "pinSha256": "6I/tDtpbWLgfvO5R4h05wGIj6KbRr61IwOkd9GqjkrI=",
            }
        ]
        create_endpoint_scan(
            e1, "tls_qualys_certificate_trusted", "trusted", datetime.now(timezone.utc), evidence=json.dumps(evidence)
        )
        create_endpoint_scan(
            e2, "tls_qualys_certificate_trusted", "trusted", datetime.now(timezone.utc), evidence=json.dumps(evidence)
        )
        create_endpoint_scan(e1, "tls_qualys_encryption_quality", "A", datetime.now(timezone.utc))
        create_endpoint_scan(e2, "tls_qualys_encryption_quality", "A", datetime.now(timezone.utc))
        plan_scan()
        plan_scan()
        plan_scan()
        plan_scan()
        plan_scan()
        plan_scan()
        # repeating this planning while it still doesnt have scans...
        assert calculate_progress() == [{"activity": 3, "amount": 8, "scanner": 22, "state": 1}]

        log.debug("Testing expired certificate")
        # create_endpoint_scan(e1, "tls_qualys_encryption_quality", "F", datetime.now(timezone.utc))
        # this does not delete endpoints...

        # add another scan with an expired certificate.
        create_endpoint_scan(
            e2,
            "tls_qualys_certificate_trusted",
            "trusted",
            datetime.now(timezone.utc),
            evidence=json.dumps(
                [
                    {
                        "subject": "CN=mijn-acc.groningen.nl",
                        "commonNames": ["mijn-acc.groningen.nl"],
                        "altNames": ["mijn-acc.groningen.nl"],
                        "notBefore": 1702015407000,
                        "notAfter": (datetime.now(timezone.utc) - timedelta(days=100)).timestamp(),
                        "issuerSubject": "CN=R3, O=Let's Encrypt, C=US",
                        "issuerLabel": "R3",
                        "sigAlg": "SHA256withRSA",
                        "revocationInfo": 2,
                        "crlURIs": [""],
                        "ocspURIs": ["http://r3.o.lencr.org"],
                        "revocationStatus": 2,
                        "crlRevocationStatus": 4,
                        "ocspRevocationStatus": 2,
                        "sgc": 0,
                        "issues": 0,
                        "sct": True,
                        "mustStaple": 0,
                        "sha1Hash": "c1f3b82b761a15945ab991ae4900bc10e65edbd8",
                        "pinSha256": "6I/tDtpbWLgfvO5R4h05wGIj6KbRr61IwOkd9GqjkrI=",
                    }
                ]
            ),
        )
        assert calculate_progress() == [{"activity": 3, "amount": 8, "scanner": 22, "state": 1}]
        plan_scan()
        assert calculate_progress() == [{"activity": 3, "amount": 9, "scanner": 22, "state": 1}]


def test_retrieve_endpoints_from_urls(db):
    u1 = Url.objects.create(url="example.com")
    u2 = Url.objects.create(url="example.nl")
    e1 = Endpoint.objects.create(url=u1, protocol="http", port="443")

    endpoints, urls_without_endpoints = retrieve_endpoints_from_urls([u1, u2], protocols=["http", "https"])

    assert endpoints == [e1]
    assert urls_without_endpoints == [u2.id]


def test_plan_follow_up_scan(db, default_scan_metadata, default_policy):
    """
    A follow up scan happens when one of the policies match with what is found.
    """
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    # Eg: make a follow up scan with a simple policy:
    tls_scanner = Scanner.objects.all().filter(python_name="tls_qualys").first()
    policy = ScanPolicy.objects.all().filter(scan_type="tls_qualys_encryption_quality", conclusion="F").first()
    follow = FollowUpScan.objects.create(follow_up_scanner=tls_scanner)
    follow.run_follow_up_on_any_of_these_policies.add(policy)

    # prepare an endpoint:
    u1 = Url.objects.create(url="pki.example.nl")
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
    # obsolete is that only scans are planned if they are not requested. Today requested means requested and
    # multiple scans can progress with just one scan running.
    assert PlannedScan.objects.all().count() == 1 + 8

    planned = PlannedScan.objects.all().last()
    assert planned.scanner.python_name == "tls_qualys"

    # plan plain_http:
    epgs = EndpointGenericScan.objects.create(
        endpoint=e1,
        rating="no_https_redirect_and_no_https_on_standard_port",
        type="plain_http",
        last_scan_moment=now,
        rating_determined_on=yesterday,
    )
    plan_follow_up_scans()
    assert PlannedScan.objects.all().count() == 2 + 11

    # this only works if there is a check that no new duplicate scans requests are added.
    # planned = PlannedScan.objects.all().last()
    # assert planned.scanner.python_name == "autoexplain_no_https_possible"
    # assert planned.url.url == "pki.example.nl"

    scan(epgs.id)
    explained = EndpointGenericScan.objects.get(id=epgs.id)
    assert explained.comply_or_explain_is_explained is True


def tests_bulk_state_changes(db, default_scan_metadata, default_policy):
    u1 = Url.objects.create(url="example1.com")
    u2 = Url.objects.create(url="example2.com")

    request(scanner="tls_qualys", activity="scan", urls=[u1, u2])
    request(scanner="tls_qualys", activity="scan", urls=[u1, u2])
    request(scanner="tls_qualys", activity="scan", urls=[u1, u2])
    request(scanner="tls_qualys", activity="scan", urls=[u1, u2])
    request(scanner="tls_qualys", activity="scan", urls=[u1, u2])

    # today we can request scans multiple times and have the state change for multiple items at once
    # so setting one to finished or picked up means that all tasks of a certain url are set to picked_up.
    # activity: str, scanner_id: int, url_id: int, state="finished", scanner_name=""
    set_scan_state(
        activity="scan",
        scanner_id=22,
        url_id=u1.id,
        from_state="requested",
        to_state="picked_up",
        scanner_name="tls_qualys",
    )

    assert PlannedScan.objects.all().count() == 10
    assert PlannedScan.objects.all().filter(state=State["requested"].value).count() == 5
    assert PlannedScan.objects.all().filter(state=State["picked_up"].value).count() == 5


def test_retry(db, default_scan_metadata, default_policy, caplog):
    with freeze_time("2020-01-01"):
        u1 = Url.objects.create(url="example2.com")
        request(scanner="tls_qualys", activity="scan", urls=[u1])
        PlannedScan.objects.all().update(state=State["picked_up"].value)

    # one year later this task has still not been processed.
    with freeze_time("2021-01-01"):
        retry()

    assert "Retried 1 planned scans for tls_qualys" in caplog.text
