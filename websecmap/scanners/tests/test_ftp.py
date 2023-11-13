from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint
from websecmap.scanners.scanner.ftp import store_when_new_or_kill_if_gone


def test_store_when_new_or_kill_if_gone(db):
    url = Url.objects.create(url="example.nl")

    # add a new endpoint a few times, should only be added once
    store_when_new_or_kill_if_gone(True, url.id, port=21, protocol="ftp", ip_version=4)
    store_when_new_or_kill_if_gone(True, url.id, port=21, protocol="ftp", ip_version=4)
    store_when_new_or_kill_if_gone(True, url.id, port=21, protocol="ftp", ip_version=4)

    assert Endpoint.objects.all().filter(is_dead=False).count() == 1

    # could not connect, so endpoint is killed
    store_when_new_or_kill_if_gone(False, url.id, port=21, protocol="ftp", ip_version=4)
    assert Endpoint.objects.all().filter(is_dead=True).count() == 1

    # revive endpoint if it is discovered again...
    store_when_new_or_kill_if_gone(True, url.id, port=21, protocol="ftp", ip_version=4)
    assert Endpoint.objects.all().filter(is_dead=False).count() == 1
    assert Endpoint.objects.all().filter(is_dead=True).count() == 0
