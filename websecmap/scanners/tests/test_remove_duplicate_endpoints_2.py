import logging
from datetime import datetime, timedelta

import pytz
from deepdiff import DeepDiff
from django.utils import timezone

from websecmap.organizations.models import Url
from websecmap.scanners.duplicates import deduplicate_all_endpoints_sequentially, deduplicate_all_scans_sequentially
from websecmap.scanners.models import Endpoint, EndpointGenericScan

log = logging.getLogger(__package__)


def test_deduplicate_all_endpoints_sequentially(db):
    # This was made to remove both "remove duplicate endpoints" and "remove short outages"
    u = Url.objects.create(url="basisbeveiliging.nl")
    u2 = Url.objects.create(url="example.com")

    # a set of duplicates:
    duplicate_properties = {"protocol": "https", "port": 443, "ip_version": 4, "is_dead": False, "url": u}
    target_ep = Endpoint.objects.create(
        **{**duplicate_properties, **{"discovered_on": datetime(2021, 7, 1, tzinfo=pytz.utc)}}
    )
    Endpoint.objects.create(**{**duplicate_properties, **{"discovered_on": datetime(2021, 7, 2, tzinfo=pytz.utc)}})
    e1 = Endpoint.objects.create(**{**duplicate_properties, **{"discovered_on": datetime(2021, 7, 3, tzinfo=pytz.utc)}})
    e2 = Endpoint.objects.create(**{**duplicate_properties, **{"discovered_on": datetime(2021, 7, 4, tzinfo=pytz.utc)}})

    # add some decoy records that should not be removed. They have to be added later as removal goes towards the past.
    Endpoint.objects.create(protocol="https", port=443, ip_version=6, is_dead=False, url=u)
    Endpoint.objects.create(protocol="https", port=444, ip_version=4, is_dead=False, url=u)
    Endpoint.objects.create(protocol="http", port=443, ip_version=4, is_dead=False, url=u)
    Endpoint.objects.create(protocol="https", port=443, ip_version=4, is_dead=False, url=u2)

    # The newest is dead, that state should be transferred all the way back to the oldest endpoint.
    # 9
    Endpoint.objects.create(
        protocol="https",
        port=443,
        ip_version=4,
        is_dead=True,
        url=u,
        discovered_on=datetime(2021, 7, 5, tzinfo=pytz.utc),
    )

    # a very, very old endpoint will not be merged as its outside of the 60 days *n-days* window.:
    # 10
    non_deleted = Endpoint.objects.create(
        protocol="https",
        port=443,
        ip_version=4,
        is_dead=False,
        url=u,
        discovered_on=datetime(2019, 7, 5, tzinfo=pytz.utc),
    )
    log.info(f"Non deleted endpoint has id: {non_deleted.id}")

    # a ver very NEW endpoint will also not be deleted
    # 11
    Endpoint.objects.create(
        protocol="https",
        port=443,
        ip_version=4,
        is_dead=False,
        url=u,
        discovered_on=datetime(2023, 7, 5, tzinfo=pytz.utc),
    )

    EndpointGenericScan.objects.create(endpoint=e1, rating_determined_on=timezone.now())
    EndpointGenericScan.objects.create(endpoint=e2, rating_determined_on=timezone.now())

    assert Endpoint.objects.all().count() == 11

    deduplicate_all_endpoints_sequentially()

    assert Endpoint.objects.all().count() == 7

    # validate that the database is not completely rewritten, that all above decoys are still in the database:
    eps = Endpoint.objects.all()
    epsdict = [
        {
            # "id": e.id,
            "discovered_on": endpoint.discovered_on,
            "protocol": endpoint.protocol,
            "port": endpoint.port,
            "ip_version": endpoint.ip_version,
            "is_dead": endpoint.is_dead,
            "url": endpoint.url.url,
        }
        for endpoint in eps
    ]
    log.info(epsdict)
    # Here you'll see that the state of the newest endpoint is transfered to the olderst one.
    # Id's are disabled, todo: have to reset sequence in test, but not too important right now.

    expected = [
        {
            # "id": 1,
            "discovered_on": datetime(2021, 7, 1, 0, 0, tzinfo=pytz.utc),
            "protocol": "https",
            "port": 443,
            "ip_version": 4,
            "is_dead": True,
            "url": "basisbeveiliging.nl",
        },
        {
            # "id": 5,
            "discovered_on": None,
            "protocol": "https",
            "port": 443,
            "ip_version": 6,
            "is_dead": False,
            "url": "basisbeveiliging.nl",
        },
        {
            # "id": 6,
            "discovered_on": None,
            "protocol": "https",
            "port": 444,
            "ip_version": 4,
            "is_dead": False,
            "url": "basisbeveiliging.nl",
        },
        {
            # "id": 7,
            "discovered_on": None,
            "protocol": "http",
            "port": 443,
            "ip_version": 4,
            "is_dead": False,
            "url": "basisbeveiliging.nl",
        },
        {
            # "id": 8,
            "discovered_on": None,
            "protocol": "https",
            "port": 443,
            "ip_version": 4,
            "is_dead": False,
            "url": "example.com",
        },
        {
            # "id": 10,
            "discovered_on": datetime(2019, 7, 5, 0, 0, tzinfo=pytz.utc),
            "protocol": "https",
            "port": 443,
            "ip_version": 4,
            "is_dead": False,
            "url": "basisbeveiliging.nl",
        },
        {
            # "id": 11,
            "discovered_on": datetime(2023, 7, 5, 0, 0, tzinfo=pytz.utc),
            "protocol": "https",
            "port": 443,
            "ip_version": 4,
            "is_dead": False,
            "url": "basisbeveiliging.nl",
        },
    ]
    DeepDiff(epsdict, expected, ignore_order=True)

    # The scans should also still be here
    assert EndpointGenericScan.objects.filter(endpoint=target_ep).count() == 2

    # scans have migrated to endpoint id 1
    # first_epgs = EndpointGenericScan.objects.filter(endpoint=target_ep).first()
    # assert first_epgs.endpoint.id == 1


def _setup_endpoint_test():
    u1 = Url.objects.create(url="basisbeveiliging.nl")
    pr = {
        "protocol": "http",
        "port": 1,
        "ip_version": 4,
        "is_dead": True,
        "url": u1,
        "discovered_on": datetime(2021, 7, 3, tzinfo=pytz.utc),
    }
    e1 = Endpoint.objects.create(**pr)
    manager = EndpointGenericScan.objects

    return e1, manager


def test_deduplicate_all_scans_sequentially_same_day(db):
    e1, manager = _setup_endpoint_test()

    # Straight forward test: Have two scans that are the same, they will be merged.
    now = timezone.now()
    then = timezone.now() - timedelta(days=1)
    # since they are both at the same time, the latest scan one is set to the latest scan, but which it is, is random.
    props = {
        "endpoint": e1,
        "rating": "1",
        "evidence": "1",
        "type": "a",
        "rating_determined_on": then,
        "last_scan_moment": now,
    }
    manager.create(**{**props, **{"comply_or_explain_is_explained": True, "comply_or_explain_explanation": "yolo"}})
    manager.create(**{**props, **{"is_the_latest_scan": True}})

    assert manager.count() == 2
    deduplicate_all_scans_sequentially()
    assert manager.count() == 1
    # Is the latest scan is ported

    scan = manager.all().first()
    log.info(scan.__dict__)
    assert scan.is_the_latest_scan is True
    assert scan.comply_or_explain_is_explained is True
    assert scan.comply_or_explain_explanation == "yolo"

    # Do it again, vice versa.
    # Now lets reverse the order of things scanned on the same day and see that stuff is copied correctly
    manager.all().delete()
    assert manager.count() == 0
    manager.create(**{**props, **{"is_the_latest_scan": True}})
    manager.create(**{**props, **{"comply_or_explain_is_explained": True, "comply_or_explain_explanation": "yolo"}})

    assert manager.count() == 2
    deduplicate_all_scans_sequentially()
    assert manager.count() == 1
    scan = manager.all().first()
    log.info(scan.__dict__)
    assert scan.comply_or_explain_is_explained is True
    assert scan.comply_or_explain_explanation == "yolo"
    assert scan.is_the_latest_scan is True


def test_deduplicate_all_scans_sequentially_with_intermediate_scan(db):
    # An intermediate scan that deviates from the current scan will not result in deletions.
    # scan 1 december: A
    # scan 2 december: B
    # scan 3 december: A
    # Conclusion: nothing is deleted because scan 2 is relevant

    e1, manager = _setup_endpoint_test()

    # Straight forward test: Have two scans that are the same, they will be merged.
    now3 = timezone.now() - timedelta(days=13)
    now2 = timezone.now() - timedelta(days=14)
    now1 = timezone.now() - timedelta(days=15)
    manager.create(endpoint=e1, rating="A", evidence="1", type="a", rating_determined_on=now1, last_scan_moment=now1)
    manager.create(endpoint=e1, rating="B", evidence="1", type="a", rating_determined_on=now2, last_scan_moment=now2)
    manager.create(endpoint=e1, rating="A", evidence="1", type="a", rating_determined_on=now3, last_scan_moment=now3)

    assert manager.count() == 3
    deduplicate_all_scans_sequentially()
    assert manager.count() == 3

    # Add another endpoint for another scan, this is not taken into consideration as the scan type is different
    manager.create(endpoint=e1, rating="A", evidence="1", type="b", rating_determined_on=now3, last_scan_moment=now3)
    deduplicate_all_scans_sequentially()
    assert manager.count() == 4

    # Add even more noise that is flipping between states, nothing will be deleted.
    now4 = timezone.now() - timedelta(days=4)
    now5 = timezone.now() - timedelta(days=5)
    now6 = timezone.now() - timedelta(days=6)
    now7 = timezone.now() - timedelta(days=7)
    now8 = timezone.now() - timedelta(days=8)
    now9 = timezone.now() - timedelta(days=9)
    now10 = timezone.now() - timedelta(days=10)
    now11 = timezone.now() - timedelta(days=11)
    now12 = timezone.now() - timedelta(days=12)

    manager.create(endpoint=e1, rating="B", evidence="1", type="a", rating_determined_on=now12, last_scan_moment=now12)
    manager.create(endpoint=e1, rating="A", evidence="1", type="a", rating_determined_on=now11, last_scan_moment=now11)
    manager.create(endpoint=e1, rating="B", evidence="1", type="a", rating_determined_on=now10, last_scan_moment=now10)
    manager.create(endpoint=e1, rating="A", evidence="1", type="a", rating_determined_on=now9, last_scan_moment=now9)
    manager.create(endpoint=e1, rating="B", evidence="1", type="a", rating_determined_on=now8, last_scan_moment=now8)
    manager.create(endpoint=e1, rating="A", evidence="1", type="a", rating_determined_on=now7, last_scan_moment=now7)
    manager.create(endpoint=e1, rating="B", evidence="1", type="a", rating_determined_on=now6, last_scan_moment=now6)
    manager.create(endpoint=e1, rating="A", evidence="1", type="a", rating_determined_on=now5, last_scan_moment=now5)
    manager.create(endpoint=e1, rating="B", evidence="1", type="a", rating_determined_on=now4, last_scan_moment=now4)

    deduplicate_all_scans_sequentially()
    assert manager.count() == 13


def test_deduplicate_all_scans_sequentially_with_noise(db):
    # Create a bunch of unique urls, endpoints and scans and verify that they are not deleted because they are all legit

    u1 = Url.objects.create(url="basisbeveiliging.nl")
    u2 = Url.objects.create(url="example.com")
    p1 = {
        "protocol": "http",
        "port": 1,
        "ip_version": 4,
        "is_dead": True,
        "url": u1,
        "discovered_on": datetime(2021, 7, 3, tzinfo=pytz.utc),
    }
    p2 = {
        "protocol": "http",
        "port": 1,
        "ip_version": 4,
        "is_dead": True,
        "url": u2,
        "discovered_on": datetime(2021, 7, 3, tzinfo=pytz.utc),
    }
    e1 = Endpoint.objects.create(**p1)
    e2 = Endpoint.objects.create(**p1)
    e3 = Endpoint.objects.create(**p1)
    e4 = Endpoint.objects.create(**p2)
    e5 = Endpoint.objects.create(**p2)
    e6 = Endpoint.objects.create(**p2)
    manager = EndpointGenericScan.objects

    now2 = timezone.now() - timedelta(days=2)
    now1 = timezone.now() - timedelta(days=3)
    manager.create(endpoint=e1, rating="A", evidence="1", type="a", rating_determined_on=now1, last_scan_moment=now1)
    manager.create(endpoint=e1, rating="B", evidence="1", type="a", rating_determined_on=now2, last_scan_moment=now2)
    manager.create(endpoint=e2, rating="A", evidence="1", type="a", rating_determined_on=now1, last_scan_moment=now1)
    manager.create(endpoint=e2, rating="B", evidence="1", type="a", rating_determined_on=now2, last_scan_moment=now2)
    manager.create(endpoint=e3, rating="A", evidence="1", type="a", rating_determined_on=now1, last_scan_moment=now1)
    manager.create(endpoint=e3, rating="B", evidence="1", type="a", rating_determined_on=now2, last_scan_moment=now2)
    manager.create(endpoint=e4, rating="A", evidence="1", type="a", rating_determined_on=now1, last_scan_moment=now1)
    manager.create(endpoint=e4, rating="B", evidence="1", type="a", rating_determined_on=now2, last_scan_moment=now2)
    manager.create(endpoint=e5, rating="A", evidence="1", type="a", rating_determined_on=now1, last_scan_moment=now1)
    manager.create(endpoint=e5, rating="B", evidence="1", type="a", rating_determined_on=now2, last_scan_moment=now2)
    manager.create(endpoint=e6, rating="A", evidence="1", type="a", rating_determined_on=now1, last_scan_moment=now1)
    manager.create(endpoint=e6, rating="B", evidence="1", type="a", rating_determined_on=now2, last_scan_moment=now2)
    manager.create(endpoint=e6, rating="A", evidence="2", type="a", rating_determined_on=now2, last_scan_moment=now2)
    manager.create(endpoint=e6, rating="A", evidence="1", type="b", rating_determined_on=now2, last_scan_moment=now2)

    assert manager.count() == 14
    deduplicate_all_scans_sequentially()
    assert manager.count() == 14


def test_deduplicate_all_scans_sequentially_in_a_sequence(db):
    e1, manager = _setup_endpoint_test()
    td = timedelta

    # See if the whole sequence is merged into one
    now = timezone.now()
    props = {"endpoint": e1, "rating": "1", "evidence": "1", "type": "a"}
    # last_scan_moment on new objects cannot be set, need to override it manually
    # auto_now_add: Note that the current date is always used; it’s not just a default value that you can override.
    a = manager.create(**{**props, **{"rating_determined_on": now - td(days=9)}})
    a.last_scan_moment = now - td(days=9)
    a.save()
    a = manager.create(**{**props, **{"rating_determined_on": now - td(days=8)}})
    a.last_scan_moment = now - td(days=8)
    a.save()
    a = manager.create(**{**props, **{"rating_determined_on": now - td(days=7)}})
    a.last_scan_moment = now - td(days=7)
    a.save()
    a = manager.create(**{**props, **{"rating_determined_on": now - td(days=6)}})
    a.last_scan_moment = now - td(days=6)
    a.save()
    # The explanation is somewhere in the middle
    a = manager.create(
        **{
            **props,
            **{
                "rating_determined_on": now - timedelta(days=5),
                "last_scan_moment": now - timedelta(days=5),
                "comply_or_explain_is_explained": True,
                "comply_or_explain_explanation": "yolo",
            },
        }
    )
    a.last_scan_moment = now - td(days=5)
    a.save()
    a = manager.create(**{**props, **{"rating_determined_on": now - td(days=4)}})
    a.last_scan_moment = now - td(days=4)
    a.save()
    a = manager.create(**{**props, **{"rating_determined_on": now - td(days=3)}})
    a.last_scan_moment = now - td(days=3)
    a.save()
    a = manager.create(**{**props, **{"rating_determined_on": now - td(days=2)}})
    a.last_scan_moment = now - td(days=2)
    a.save()
    a = manager.create(**{**props, **{"rating_determined_on": now - td(days=1), "is_the_latest_scan": True}})
    a.last_scan_moment = now - td(days=1)
    a.save()

    assert manager.count() == 9
    deduplicate_all_scans_sequentially()
    assert manager.count() == 1

    scan = manager.all().first()
    log.info(scan.__dict__)
    assert scan.is_the_latest_scan is True
    assert scan.comply_or_explain_is_explained is True
    assert scan.comply_or_explain_explanation == "yolo"
    # make sure the last scan moment is also get migrated correctly
    assert scan.last_scan_moment == now - td(days=1)
