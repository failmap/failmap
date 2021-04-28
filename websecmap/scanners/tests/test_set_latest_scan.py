from django.utils.timezone import now

from websecmap.organizations.models import Url
from websecmap.scanners.management.commands.set_latest_scan import reflag_endpointgenericscan
from websecmap.scanners.models import EndpointGenericScan, Endpoint


def test_reflag_endpointgenericscan(db):
    u = Url.objects.create(url="basisbeveiliging.nl")
    e = Endpoint.objects.create(protocol="https", port=443, ip_version=4, is_dead=False, url=u)

    # scans for first endpoint
    args = {"type": "tls_qualys", "last_scan_moment": now(), "endpoint": e, "rating_determined_on": now()}
    e1 = EndpointGenericScan.objects.create(**args)
    e2 = EndpointGenericScan.objects.create(**args)
    e3 = EndpointGenericScan.objects.create(**args)
    e4 = EndpointGenericScan.objects.create(
        type="myscanner", last_scan_moment=now(), endpoint=e, rating_determined_on=now()
    )

    # other endpoint
    othere = Endpoint.objects.create(protocol="https", port=443, ip_version=4, is_dead=False, url=u)
    args = {"type": "tls_qualys", "last_scan_moment": now(), "endpoint": othere, "rating_determined_on": now()}
    othere1 = EndpointGenericScan.objects.create(**args)
    othere2 = EndpointGenericScan.objects.create(**args)

    # running multiple times does not matter
    reflag_endpointgenericscan("tls_qualys")
    reflag_endpointgenericscan("tls_qualys")
    reflag_endpointgenericscan("tls_qualys")

    e1 = EndpointGenericScan.objects.get(id=e1.pk)
    assert e1.is_the_latest_scan is False

    e2 = EndpointGenericScan.objects.get(id=e2.pk)
    assert e2.is_the_latest_scan is False

    # highest ID is affected
    e3 = EndpointGenericScan.objects.get(id=e3.pk)
    assert e3.is_the_latest_scan is True

    # Other scan is not affected
    e4 = EndpointGenericScan.objects.get(id=e4.pk)
    assert e4.is_the_latest_scan is False

    # other endpoint
    e2 = EndpointGenericScan.objects.get(id=othere1.pk)
    assert e2.is_the_latest_scan is False

    # highest ID is affected
    e3 = EndpointGenericScan.objects.get(id=othere2.pk)
    assert e3.is_the_latest_scan is True
