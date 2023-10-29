import pytest

from websecmap.organizations.models import Url
from websecmap.scanners.models import UrlIp
from websecmap.scanners.scanner.resolve_ip import clean_ips, store_ip


@pytest.mark.parametrize("is_v4", [True, False])
def test_store_ip(db, is_v4):
    url = Url.objects.create(url="basisbeveiliging.nl")

    # new address
    store_ip(url=url, is_v4=is_v4, ip="127.0.0.1", ips_in_dns=["127.0.0.1"])
    stored = UrlIp.objects.first()
    assert stored.ip == "127.0.0.1"
    assert stored.is_v4 is is_v4
    assert stored.is_unused is False

    # changed address should disable the other one.
    store_ip(url=url, is_v4=is_v4, ip="127.0.0.2", ips_in_dns=["127.0.0.2", "127.0.0.3"])
    stored = UrlIp.objects.last()
    assert stored.ip == "127.0.0.2"
    assert stored.is_v4 is is_v4
    assert stored.is_unused is False

    stored = UrlIp.objects.first()
    assert stored.ip == "127.0.0.1"
    assert stored.is_v4 is is_v4
    assert stored.is_unused is True

    # old address should be revived, other .2 is now unused
    store_ip(url=url, is_v4=is_v4, ip="127.0.0.1", ips_in_dns=["127.0.0.1"])
    stored = UrlIp.objects.last()
    assert stored.ip == "127.0.0.2"
    assert stored.is_v4 is is_v4
    assert stored.is_unused is True

    # an different IP has been received but the DNS does contain the already known address, so
    # 127.0.0.1 is kept, the previous 127.0.0.2 is made unused, as that is not in the response.
    store_ip(url=url, is_v4=is_v4, ip="127.0.0.4", ips_in_dns=["127.0.0.1", "127.0.0.4"])
    stored = UrlIp.objects.filter(url=url, is_unused=False).first()
    assert stored.ip == "127.0.0.1"
    assert stored.is_v4 is is_v4
    assert stored.is_unused is False

    stored = UrlIp.objects.filter(url=url, is_unused=True).first()
    assert stored.ip == "127.0.0.2"
    assert stored.is_v4 is is_v4
    assert stored.is_unused is True

    # and delete it, everything should be gone
    clean_ips(url, is_v4=True)
    stored = UrlIp.objects.last()
    assert stored.ip == "127.0.0.2"
    assert stored.is_v4 is is_v4
    assert stored.is_unused is True

    stored = UrlIp.objects.filter(url=url, is_v4=True, is_unused=False)
    assert stored.count() == 0
