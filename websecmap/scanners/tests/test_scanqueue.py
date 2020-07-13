import logging

from websecmap.organizations.models import Organization, Url
from websecmap.scanners.models import Endpoint, EndpointScanQueue, EndpointScanQueueLog
from websecmap.scanners.scanqueue import pickup, queue, update_state_on_endpoint_scan

log = logging.getLogger('websecmap')


def create_organization(name="Test"):
    o = Organization()
    o.name = name
    o.save()
    return o


def create_url(url: str = "example.com"):
    u = Url()
    u.url = url
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
    e.save()
    return e


def test_scanqueue(db):

    o = create_organization("Test")
    u = create_url("example.com")
    u = link_url_to_organization(u, o)
    e4 = create_endpoint(u, 4, "https", 443)
    e6 = create_endpoint(u, 6, "https", 443)

    # register scans on both endpoints:
    scan1 = queue(e4, "tlsq")  # noqa
    scan2 = queue(e6, "tlsq")  # noqa
    assert EndpointScanQueue.objects.count() == 2
    assert EndpointScanQueueLog.objects.count() == 2

    # changes to the state are logged from the queue itself. We don't have to keep track on that.
    update_state_on_endpoint_scan(e4, "tlsq", "random_new_state")
    assert EndpointScanQueue.objects.count() == 2
    assert EndpointScanQueueLog.objects.count() == 3

    # writing the same state, does not create a new log object:
    update_state_on_endpoint_scan(e4, "tlsq", "random_new_state")
    assert EndpointScanQueueLog.objects.count() == 3

    # register a third scan, that should not be picked up:
    scan3 = queue(e6, "http_security_headers")  # noqa

    # pickup 20 scans from the queue to scan them, the picked up items will have a log item telling they are picked up
    # only one scan is picked up, because the e4 does not have a 'queued' state.
    picked_up = pickup("tlsq", 1000)
    assert len(picked_up) == 1
    assert EndpointScanQueueLog.objects.count() == 4

    # if you pick it up again, nothing is picked up:
    picked_up = pickup("tlsq", 2000)
    assert len(picked_up) == 0
    assert EndpointScanQueueLog.objects.count() == 4
