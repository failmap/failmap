"""Integration tests of scanner commands."""

import json
from datetime import datetime, timezone

from django.core.management import call_command

from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.scanner.security_headers import analyze_website_headers, measure_hsts_header

SECURITY_HEADERS = {
    "X-XSS-Protection": "1",
}

TEST_ORGANIZATION = "faalonië"
NON_EXISTING_ORGANIZATION = "faaloniet"


def test_security_headers(responses, db, faaloniae, default_scan_metadata):
    """Test running security headers scan."""

    responses.add(responses.GET, "https://" + faaloniae["url"].url + ":443/", headers=SECURITY_HEADERS)

    result = json.loads(call_command("scan", "security_headers", "-v3", "-o", TEST_ORGANIZATION))
    # the result of scan headers was {'status': 'success'} but the planned scan task has changed that to None
    assert result[0] is None


def test_security_headers_all(responses, db, faaloniae, default_scan_metadata):
    """Test defaulting to all organizations."""

    responses.add(responses.GET, "https://" + faaloniae["url"].url + ":443/", headers=SECURITY_HEADERS)

    result = json.loads(call_command("scan", "security_headers", "-v3"))
    print(result)
    assert result[0] is None


def test_security_headers_notfound(responses, db, faaloniae, default_scan_metadata):
    """Test invalid organization."""

    # should work fine, it will start a scan on nothing, so it's done quickly :)
    result = json.loads(call_command("scan", "security_headers", "-v3", "-o", NON_EXISTING_ORGANIZATION))
    # no crashes, just an empty result.
    assert result == []


# todo: could do a redirect test
def test_security_headers_failure(responses, db, faaloniae, default_scan_metadata):
    """Test with failing endpoint."""

    responses.add(responses.GET, "https://" + faaloniae["url"].url + ":443/", status=500)

    result = json.loads(call_command("scan", "security_headers", "-v3", "-o", TEST_ORGANIZATION))
    print(result)
    assert result[0] is None


def test_analyze_website_headers(db):
    u = Url.objects.create(url="basisbeveiliging.nl")
    ep = Endpoint.objects.create(
        **{
            "protocol": "https",
            "port": 443,
            "ip_version": 4,
            "is_dead": False,
            "url": u,
            "discovered_on": datetime(2021, 7, 1, tzinfo=timezone.utc),
        }
    )

    headers = [
        {
            "request": 1,
            "url": "https://www.basisbeveiliging.nl/",
            "protocol": "https",
            "status_code": 200,
            "content_type": "text/html; charset=utf-8",
            "headers": {},
        }
    ]

    analyze_website_headers(ep.id, u.id, "https", headers)
    analyze_website_headers(ep.id, u.id, "https", headers)
    analyze_website_headers(ep.id, u.id, "https", headers)
    # all six headers missing
    assert EndpointGenericScan.objects.all().count() == 6

    headers = [
        {
            "request": 1,
            "url": "https://www.basisbeveiliging.nl/",
            "protocol": "https",
            "status_code": 200,
            "content_type": "text/html; charset=utf-8",
            "headers": {
                "Content-Length": "2976",
                "Content-Type": "text/html; charset=utf-8",
                "Date": "Wed, 08 Feb 2023 14:24:00 GMT",
                "Access-Control-Expose-Headers": "Request-Context",
                "Cache-Control": "private",
                "Content-Encoding": "gzip",
                "Vary": "Accept-Encoding",
                "P3P": 'CP="CAO COR CURa ADMa DEVa OUR IND ONL COM DEM PRE"',
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "ReFeRrer-Policy": "no-referrer-when-downgrade",
                "CoNteNt-Security-Policy": "default-src * data: 'unsafe-inline' 'unsafe-hashes' 'unsafe-eval'",
                "STRICT-Transport-Security": "max-age=63072000; includeSubDomains;",
                "permissions-Policy": "camera=(self), fullscreen=(self), usb=*",
            },
        }
    ]
    analyze_website_headers(ep.id, u.id, "https", headers)
    analyze_website_headers(ep.id, u.id, "https", headers)
    analyze_website_headers(ep.id, u.id, "https", headers)

    # all six present :)
    assert EndpointGenericScan.objects.all().count() == 12

    # all six gone again:
    headers = [
        {
            "request": 1,
            "url": "https://www.basisbeveiliging.nl/",
            "protocol": "https",
            "status_code": 200,
            "content_type": "text/html; charset=utf-8",
            "headers": {},
        }
    ]
    analyze_website_headers(ep.id, u.id, "https", headers)
    assert EndpointGenericScan.objects.all().count() == 18


def test_measure_hsts_header():
    # when no hsts header is present, but there is no https site, this will result in a not applicable

    # straight forward use case: https site has hsts, so ok.
    headers = [
        {
            "request": 1,
            "url": "https://www.basisbeveiliging.nl/",
            "protocol": "https",
            "headers": {
                "STRICT-Transport-Security": "max-age=63072000; includeSubDomains;",
            },
        }
    ]
    assert measure_hsts_header(headers) == "present"

    # third request on the same host has hsts, so ok:
    headers = [
        {
            "request": 1,
            "url": "https://www.basisbeveiliging.nl/",
            "protocol": "https",
            "headers": {},
        },
        {
            "request": 2,
            "url": "https://www.basisbeveiliging.nl/",
            "protocol": "https",
            "headers": {},
        },
        {
            "request": 3,
            "url": "https://www.basisbeveiliging.nl/",
            "protocol": "https",
            "headers": {
                "STRICT-Transport-Security": "max-age=63072000; includeSubDomains;",
            },
        },
    ]
    assert measure_hsts_header(headers) == "present"

    # first request on another host does NOT have hsts, but the final site does. So here a missing is returned:
    headers = [
        {
            "request": 1,
            "url": "https://www.nu.nl/",
            "protocol": "https",
            "headers": {},
        },
        {
            "request": 2,
            "url": "https://www.basisbeveiliging.nl/",
            "protocol": "https",
            "headers": {},
        },
        {
            "request": 3,
            "url": "https://www.basisbeveiliging.nl/",
            "protocol": "https",
            "headers": {
                "STRICT-Transport-Security": "max-age=63072000; includeSubDomains;",
            },
        },
    ]
    assert measure_hsts_header(headers) == "missing"

    # the first site is a http site, in that case no HSTS is needed and the second site has https, so that will need it:
    headers = [
        {
            "request": 1,
            "url": "http://www.nu.nl/",
            "protocol": "http",
            "headers": {},
        },
        {
            "request": 2,
            "url": "https://www.basisbeveiliging.nl/",
            "protocol": "https",
            "headers": {},
        },
        {
            "request": 3,
            "url": "https://www.basisbeveiliging.nl/",
            "protocol": "https",
            "headers": {
                "STRICT-Transport-Security": "max-age=63072000; includeSubDomains;",
            },
        },
    ]
    assert measure_hsts_header(headers) == "present"

    # all sites are http, so no hsts is needed:
    headers = [
        {
            "request": 1,
            "url": "http://www.nu.nl/",
            "protocol": "http",
            "headers": {},
        },
        {
            "request": 2,
            "url": "http://www.basisbeveiliging.nl/",
            "protocol": "http",
            "headers": {},
        },
        {
            "request": 3,
            "url": "http://www.basisbeveiliging.nl/",
            "protocol": "http",
            "headers": {},
        },
    ]
    assert measure_hsts_header(headers) == "not_applicable"
