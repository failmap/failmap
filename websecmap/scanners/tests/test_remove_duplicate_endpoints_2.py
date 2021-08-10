from datetime import date, datetime

import pytz
from django.utils import timezone

from websecmap.organizations.models import Url
from websecmap.scanners.duplicates import deduplicate_all_endpoints_sequentially
from websecmap.scanners.models import Endpoint, EndpointGenericScan
import logging

log = logging.getLogger(__package__)


def test_deduplicate_all_endpoints_sequentially(db):
    # This was made to remove both "remove duplicate endpoints" and "remove short outages"
    u = Url.objects.create(url="basisbeveiliging.nl")
    u2 = Url.objects.create(url="example.com")

    # a set of duplicates:
    duplicate_properties = {"protocol": "https", "port": 443, "ip_version": 4, "is_dead": False, "url": u}
    target_ep = Endpoint.objects.create(**{**duplicate_properties, **{"discovered_on": date(2021, 7, 1)}})
    Endpoint.objects.create(**{**duplicate_properties, **{"discovered_on": date(2021, 7, 2)}})
    e1 = Endpoint.objects.create(**{**duplicate_properties, **{"discovered_on": date(2021, 7, 3)}})
    e2 = Endpoint.objects.create(**{**duplicate_properties, **{"discovered_on": date(2021, 7, 4)}})

    # add some decoy records that should not be removed. They have to be added later as removal goes towards the past.
    Endpoint.objects.create(protocol="https", port=443, ip_version=6, is_dead=False, url=u)
    Endpoint.objects.create(protocol="https", port=444, ip_version=4, is_dead=False, url=u)
    Endpoint.objects.create(protocol="http", port=443, ip_version=4, is_dead=False, url=u)
    Endpoint.objects.create(protocol="https", port=443, ip_version=4, is_dead=False, url=u2)

    # The newest is dead, that state should be transferred all the way back to the oldest endpoint.
    # 9
    Endpoint.objects.create(
        protocol="https", port=443, ip_version=4, is_dead=True, url=u, discovered_on=date(2021, 7, 5)
    )

    # a very, very old endpoint will not be merged as its outside of the 60 days *n-days* window.:
    # 10
    non_deleted = Endpoint.objects.create(
        protocol="https", port=443, ip_version=4, is_dead=False, url=u, discovered_on=date(2019, 7, 5)
    )
    log.info(f"Non deleted endpoint has id: {non_deleted.id}")

    # a ver very NEW endpoint will also not be deleted
    # 11
    Endpoint.objects.create(
        protocol="https", port=443, ip_version=4, is_dead=False, url=u, discovered_on=date(2023, 7, 5)
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
            "discovered_on": e.discovered_on,
            "protocol": e.protocol,
            "port": e.port,
            "ip_version": e.ip_version,
            "is_dead": e.is_dead,
            "url": e.url.url,
        }
        for e in eps
    ]
    log.info(epsdict)
    # Here you'll see that the state of the newest endpoint is transfered to the olderst one.
    # Id's are disabled, todo: have to reset sequence in test, but not too important right now.
    assert epsdict == [
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

    # The scans should also still be here
    assert EndpointGenericScan.objects.filter(endpoint=target_ep).count() == 2

    # scans have migrated to endpoint id 1
    # first_epgs = EndpointGenericScan.objects.filter(endpoint=target_ep).first()
    # assert first_epgs.endpoint.id == 1
