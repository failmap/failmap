from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, HttpEndpointHeaders
from websecmap.scanners.scanner.endpoint_headers import store


def test_endpoint_headers_store(db):
    url = Url.objects.create(url="example.nl")
    ep = Endpoint.objects.create(url=url, port=80, protocol="http")

    response = {
        "headers": {"Content-Type": "text/html; charset=UTF-8"},
        "header_names": {"content-type": ""},
    }

    store(response, ep.id)
    assert HttpEndpointHeaders.objects.all().count() == 1

    # check if has_keys will work, all headers need to be in a dict, with they keys present:
    first = HttpEndpointHeaders.objects.first()
    assert first.header_names == {"content-type": ""}

    # storing the same stuff does not create a new record, even if there are other unstable headers:
    response = {
        "headers": {"Content-Type": "text/html; charset=UTF-8", "unstable": "random content"},
        "header_names": {"content-type": ""},
    }
    store(response, ep.id)
    assert HttpEndpointHeaders.objects.all().count() == 1

    # content type change means there is a new record... It's now a json response...
    response = {
        "headers": {"Content-Type": "application/json", "unstable": "random content"},
        "header_names": {"content-type": ""},
    }
    store(response, ep.id)
    assert HttpEndpointHeaders.objects.all().count() == 2

    # store this in a new endpoint makes a new record
    ep2 = Endpoint.objects.create(url=url, port=443, protocol="http")
    store(response, ep2.id)
    assert HttpEndpointHeaders.objects.all().count() == 3
