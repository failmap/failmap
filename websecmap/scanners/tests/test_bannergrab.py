import json
from datetime import datetime, timedelta, timezone

from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan, UrlIp
from websecmap.scanners.scanner.bannergrab_masscan import clean_old_bannergrab_results, handle_masscan_output
from websecmap.scanners.scanner.banners.detect_version import (
    SERVICE_IDENTITY_LIKELY_VERSION_FOUND,
    SERVICE_IDENTITY_NOT_SEEN_IN_A_WHILE,
)


def test_handle_masscan_output(db, current_path):
    """
    "93.93.121.121": [
            {
                "port": 80,
                "proto": "tcp",
                "status": "open",
                "reason": "syn-ack",
                "ttl": 53
            },
            {
                "port": 443,
                "proto": "tcp",
                "status": "open",
                "reason": "syn-ack",
                "ttl": 53
            },
            {
                "port": 80,
                "proto": "tcp",
                "service": {
                    "name": "http.server",
                    "banner": "Apache/2.4.25 (Debian)"
                }
            },
            {
                "port": 80,
                "proto": "tcp",
                "service": {
                    "name": "title",
                    "banner": "Een ogenblik geduld alstublieft"
                }
            },
            {
                "port": 80,
                "proto": "tcp",
                "service": {
                    "name": "http",
                    "banner": "HTTP/1.1 200 OK\r\nDate: Wed, 23 Nov 2022 19:53:44 GMT\r\nServer: Apache/2.4.25 (...
                }
            },
            {
                "port": 443,
                "proto": "tcp",
                "service": {
                    "name": "ssl",
                    "banner": " ALERT(0x0246) "
                }
            }
        ],

    The 'title' protocol is not supported, so it will not be added.
    ssl doesn't add anything except an open port.
    it can be reduced to a banner if it contains the text 'version' perhaps.
    """

    with open(f"{current_path}/websecmap/scanners/tests/bannergrab/py_masscan_out.json") as f:
        data = json.load(f)

    # nothing sticks because nothing is in the database. But it should not crash.
    handle_masscan_output(data)

    # add some urls and related ips, then there should be endpoints and results.
    # 93.93.121.121 == Apache/2.4.25 (Debian)
    url = Url.objects.create(url="internetcleanup.foundation")
    UrlIp.objects.create(url=url, ip="93.93.121.121", is_v4=True, discovered_on=datetime.now(timezone.utc))

    # now add a rule
    handle_masscan_output(data)

    # the endpoint should be created with a link to the url because the ip matches.
    assert Endpoint.objects.all().count() == 1
    ep1 = Endpoint.objects.all().first()
    assert ep1.protocol == "http"
    assert ep1.url is not None
    assert ep1.url.id == url.id

    # # todo: this can create junk protocols
    # ep2 = Endpoint.objects.all().last()
    # assert ep2.protocol == "title"

    assert EndpointGenericScan.objects.all().count() == 1
    # epgs = EndpointGenericScan.objects.all().first()
    # assert epgs.evidence == "Een ogenblik geduld alstublieft"
    # assert epgs.rating == SERVICE_IDENTITY_SOME_IDENTITY_FOUND

    epgs = EndpointGenericScan.objects.all().last()
    assert epgs.evidence == "apache/2.4.25 (debian)"
    assert epgs.rating == SERVICE_IDENTITY_LIKELY_VERSION_FOUND

    # clean old banners, nothing happens now because all results are new:
    clean_old_bannergrab_results()
    epgs = EndpointGenericScan.objects.all().last()
    assert epgs.evidence == "apache/2.4.25 (debian)"
    assert epgs.rating == SERVICE_IDENTITY_LIKELY_VERSION_FOUND

    # make it an old result:
    epgs.last_scan_moment = datetime.now(timezone.utc) - timedelta(days=100)
    epgs.save()

    clean_old_bannergrab_results()
    assert EndpointGenericScan.objects.all().count() == 2
    epgs = EndpointGenericScan.objects.all().first()
    assert epgs.evidence == ""
    assert epgs.rating == SERVICE_IDENTITY_NOT_SEEN_IN_A_WHILE
