from django.utils import timezone

from websecmap.organizations.models import Url
from websecmap.scanners.management.commands.remove_duplicate_alive_endpoints import remove_duplicate_endpoints
from websecmap.scanners.models import Endpoint, EndpointGenericScan


def test_remove_duplicate_endpoints(db):
    u = Url.objects.create(url="basisbeveiliging.nl")
    u2 = Url.objects.create(url="example.com")

    # add some decoy records that should not be removed.
    Endpoint.objects.create(protocol="https", port=443, ip_version=6, is_dead=False, url=u)
    Endpoint.objects.create(protocol="https", port=444, ip_version=4, is_dead=False, url=u)
    Endpoint.objects.create(protocol="http", port=443, ip_version=4, is_dead=False, url=u)
    Endpoint.objects.create(protocol="https", port=443, ip_version=4, is_dead=False, url=u2)
    Endpoint.objects.create(protocol="https", port=443, ip_version=4, is_dead=True, url=u)

    target_ep = Endpoint.objects.create(protocol="https", port=443, ip_version=4, is_dead=False, url=u)
    Endpoint.objects.create(protocol="https", port=443, ip_version=4, is_dead=False, url=u)
    e1 = Endpoint.objects.create(protocol="https", port=443, ip_version=4, is_dead=False, url=u)
    e2 = Endpoint.objects.create(protocol="https", port=443, ip_version=4, is_dead=False, url=u)

    EndpointGenericScan.objects.create(endpoint=e1, rating_determined_on=timezone.now())
    EndpointGenericScan.objects.create(endpoint=e2, rating_determined_on=timezone.now())

    assert Endpoint.objects.all().count() == 9

    remove_duplicate_endpoints()

    assert Endpoint.objects.all().count() == 6

    # validate that the database is not completely rewritten, that all above decoys are still in the dabtabase.:
    eps = Endpoint.objects.all()
    epsdict = [
        {"protocol": e.protocol, "port": e.port, "ip_version": e.ip_version, "is_dead": e.is_dead, "url": e.url.url}
        for e in eps
    ]
    assert epsdict == [
        {"ip_version": 6, "is_dead": False, "port": 443, "protocol": "https", "url": "basisbeveiliging.nl"},
        {"ip_version": 4, "is_dead": False, "port": 444, "protocol": "https", "url": "basisbeveiliging.nl"},
        {"ip_version": 4, "is_dead": False, "port": 443, "protocol": "http", "url": "basisbeveiliging.nl"},
        {"ip_version": 4, "is_dead": False, "port": 443, "protocol": "https", "url": "example.com"},
        {"ip_version": 4, "is_dead": True, "port": 443, "protocol": "https", "url": "basisbeveiliging.nl"},
        {"ip_version": 4, "is_dead": False, "port": 443, "protocol": "https", "url": "basisbeveiliging.nl"},
    ]

    assert EndpointGenericScan.objects.filter(endpoint=target_ep).count() == 2
