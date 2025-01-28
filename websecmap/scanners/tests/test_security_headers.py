"""Integration tests of scanner commands."""

import json
from datetime import datetime, timezone

from django.core.management import call_command

from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.scanner.security_headers import (
    analyze_website_headers,
    clean_csp_header,
    measure_hsts_header,
    remove_guid_from_string,
    remove_random_identifiers,
    remove_timestamp_from_end_of_string,
)

SECURITY_HEADERS = {
    "X-XSS-Protection": "1",
}

TEST_ORGANIZATION = "faalonië"
NON_EXISTING_ORGANIZATION = "faaloniet"


def test_security_headers(responses, db, faaloniae, default_scan_metadata):
    """Test running security headers scan."""

    responses.add(responses.GET, "https://" + faaloniae["url"].url + ":443/", headers=SECURITY_HEADERS)

    result = json.loads(call_command("scan", "security_headers", "-v3", "-o", TEST_ORGANIZATION))
    assert result[0] == {"status": "success"}


def test_security_headers_all(responses, db, faaloniae, default_scan_metadata):
    """Test defaulting to all organizations."""

    responses.add(responses.GET, "https://" + faaloniae["url"].url + ":443/", headers=SECURITY_HEADERS)

    result = json.loads(call_command("scan", "security_headers", "-v3"))
    assert result[0] == {"status": "success"}


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
    assert result[0] == {"status": "success"}


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


def test_test_clean_csp_header():
    data = (
        "default-src 'self'; base-uri 'self'; img-src * data:; frame-src 'self' https://kaart.pdok.nl "
        "https://websurveys2.govmetric.com https://app-eu.readspeaker.com https://www.youtube-nocookie.com "
        "https://www.youtube.com https://content.googleapis.com/ https://vars.hotjar.com; frame-ancestors 'self'; "
        "manifest-src 'self'; media-src 'self' blob:; script-src 'self' "
        "'nonce-NGQyYTkyOGYtNWMxNy00MjYyLWFiZWEtOWRkYTY3YmYwMDM5' "
        "https://stats.pusher.com https://www.browsealoud.com https://www.googletagmanager.com "
        "https://www.google-analytics.com https://apis.google.com https://maps.googleapis.com "
        "https://siteimproveanalytics.com https://cloudstatic.obi4wan.com https://websurveys2.govmetric.com "
        "https://platform.hireserve.nl https://websurveys2.servmetric.com https://cdn1.readspeaker.com "
        "https://cdn-eu.readspeaker.com https://virtuele-gemeente-assistent.nl https://static.hotjar.com "
        "https://script.hotjar.com https://connect.facebook.net https://snap.licdn.com https://*.timeblockr.com; "
        "connect-src 'self' https://sockjs-eu.pusher.com wss://ws-eu.pusher.com https://vttts-eu.readspeaker.com "
        "https://cloudstatic.obi4wan.com https://chatapi.obi4wan.com https://media-eu.readspeaker.com "
        "https://rstts-eu.readspeaker.com https://www.browsealoud.com https://plus.browsealoud.com "
        "https://speech.speechstream.net https://speech-eu.speechstream.net "
        "https://www.google-analytics.com https://maps.googleapis.com https://region1.google-analytics.com "
        "https://stats.g.doubleclick.net https://app.obi4wan.ai https://app-eu.readspeaker.com/ "
        "https://hitcounter.govmetric.com https://platform.hireserve.nl/ https://cdn1.readspeaker.com "
        "https://maps.googleapis.com https://virtuele-gemeente-assistent.nl wss://virtuele-gemeente-assistent.nl "
        "ws://virtuele-gemeente-assistent.nl https://in.hotjar.com https://www.facebook.com "
        "https://cdn.linkedin.oribi.io https://*.timeblockr.com; object-src 'self' https://kaart.pdok.nl; "
        "style-src 'self' data: 'nonce-NGQyYTkyOGYtNWMxNy00MjYyLWFiZWEtOWRkYTY3YmYwMDM5' "
        "https://fonts.googleapis.com https://platform.hireserve.nl https://websurveys2.servmetric.com "
        "https://cdn1.readspeaker.com https://websurveys2.govmetric.com https://virtuele-gemeente-assistent.nl "
        "https://mijn.virtuele-gemeente-assistent.nl https://maps.googleapis.com/ "
        "https://siteimproveanalytics.com https://*.timeblockr.com; font-src 'self' data: "
        "https://fonts.gstatic.com https://cdn1.readspeaker.com https://script.hotjar.com https://*.timeblockr.com;"
    )
    clean_data = clean_csp_header(data)

    assert (
        clean_data == "default-src 'self'; base-uri 'self'; img-src * data:; frame-src 'self' "
        "https://kaart.pdok.nl "
        "https://websurveys2.govmetric.com https://app-eu.readspeaker.com https://www.youtube-nocookie.com "
        "https://www.youtube.com https://content.googleapis.com/ https://vars.hotjar.com; frame-ancestors 'self'; "
        "manifest-src 'self'; media-src 'self' blob:; script-src 'self' "
        "'nonce-<TOKEN_OR_ID>' "
        "https://stats.pusher.com https://www.browsealoud.com https://www.googletagmanager.com "
        "https://www.google-analytics.com https://apis.google.com https://maps.googleapis.com "
        "https://siteimproveanalytics.com https://cloudstatic.obi4wan.com https://websurveys2.govmetric.com "
        "https://platform.hireserve.nl https://websurveys2.servmetric.com https://cdn1.readspeaker.com "
        "https://cdn-eu.readspeaker.com https://virtuele-gemeente-assistent.nl https://static.hotjar.com "
        "https://script.hotjar.com https://connect.facebook.net https://snap.licdn.com https://*.timeblockr.com; "
        "connect-src 'self' https://sockjs-eu.pusher.com wss://ws-eu.pusher.com https://vttts-eu.readspeaker.com "
        "https://cloudstatic.obi4wan.com https://chatapi.obi4wan.com https://media-eu.readspeaker.com "
        "https://rstts-eu.readspeaker.com https://www.browsealoud.com https://plus.browsealoud.com "
        "https://speech.speechstream.net https://speech-eu.speechstream.net "
        "https://www.google-analytics.com https://maps.googleapis.com https://region1.google-analytics.com "
        "https://stats.g.doubleclick.net https://app.obi4wan.ai https://app-eu.readspeaker.com/ "
        "https://hitcounter.govmetric.com https://platform.hireserve.nl/ https://cdn1.readspeaker.com "
        "https://maps.googleapis.com https://virtuele-gemeente-assistent.nl wss://virtuele-gemeente-assistent.nl "
        "ws://virtuele-gemeente-assistent.nl https://in.hotjar.com https://www.facebook.com "
        "https://cdn.linkedin.oribi.io https://*.timeblockr.com; object-src 'self' https://kaart.pdok.nl; "
        "style-src 'self' data: 'nonce-<TOKEN_OR_ID>' "
        "https://fonts.googleapis.com https://platform.hireserve.nl https://websurveys2.servmetric.com "
        "https://cdn1.readspeaker.com https://websurveys2.govmetric.com https://virtuele-gemeente-assistent.nl "
        "https://mijn.virtuele-gemeente-assistent.nl https://maps.googleapis.com/ "
        "https://siteimproveanalytics.com https://*.timeblockr.com; font-src 'self' data: "
        "https://fonts.gstatic.com https://cdn1.readspeaker.com https://script.hotjar.com https://*.timeblockr.com;"
    )

    assert clean_csp_header("default-src 'self'; base-uri 'self';") == "default-src 'self'; base-uri 'self';"

    assert (
        clean_csp_header("manifest-src 'self'; media-src 'self' blob:; script-src 'self' " "'nonce-<TOKEN_OR_ID>' ")
        == "manifest-src 'self'; media-src 'self' blob:; script-src 'self' "
        "'nonce-<TOKEN_OR_ID>' "
    )


def test_remove_guid_from_string():
    result = remove_guid_from_string("mijnantoor.nl%2Fview%2FEGW0001&state=d32e16a3-1474-4861-a954-cc481b8aa509&logie")
    assert result == "mijnantoor.nl%2Fview%2FEGW0001&state=GUID&logie"

    result = remove_guid_from_string("d32e16a3-1474-4861-a954-cc481b8aa509 d32e16a3-1474-4861-a954-cc481b8aa509")
    assert result == "GUID GUID"

    result = remove_guid_from_string("d32e16a3-1474-4861-a954 -cc481b8aa509")
    assert result == "d32e16a3-1474-4861-a954 -cc481b8aa509"
    # Other typeof guid? ->                               d32e16a3-1474-4861-a954-cc481b8aa509
    result = remove_guid_from_string(
        "https://example.com/a70b84b3-958e-00b0-08f0-9a2526e8360b/d32e16a3-1474-4861-a954-cc481b8aa509/2.jpg"
    )
    assert result == "https://example.com/GUID/GUID/2.jpg"

    # and another wrong one: f460367f-32cd-b82f-f0ef-f630d2e72ef4
    result = remove_guid_from_string("test f460367f-32cd-b82f-f0ef-f630d2e72ef4 string")
    assert result == "test GUID string"

    # Also support mixed-case guids:
    result = remove_guid_from_string("test D32E16A3-1474-4861-A954-CC481b8aa509 string")
    assert result == "test GUID string"


def test_remove_timestamp_from_end_of_string():
    # only at the end of the string, as that is the usual place for it to be.
    result = remove_timestamp_from_end_of_string("https://example.com/page.html?a=b&t=1629237157")
    assert result == "https://example.com/page.html?a=b&t=TIMESTAMP"

    # not from the middle parameters
    result = remove_timestamp_from_end_of_string("https://example.com/page.html?timestamp=1629237157&foo=bar")
    assert result == "https://example.com/page.html?timestamp=1629237157&foo=bar"

    # not as part of a path
    result = remove_timestamp_from_end_of_string("https://example.com/1629237157/test")
    assert result == "https://example.com/1629237157/test"


def test_remove_random_identifiers():
    result = remove_random_identifiers("jsessionid=node01irvw903rcwj11vvq4a24xppxp39.node0?wicket-crypt=b498kOL9W4Y&x")
    assert result == "jsessionid=<TOKEN_OR_ID>.node0?wicket-crypt=<TOKEN_OR_ID>&x"

    result = remove_random_identifiers("jsessionid=node01irvw903rcwj11vvq4a24xppxp39.node0?wicket-crypt=b498kOL9W4Y")
    assert result == "jsessionid=<TOKEN_OR_ID>.node0?wicket-crypt=<TOKEN_OR_ID>"

    result = remove_random_identifiers("jsessionid=node01irvw903rcwj11vvq4a24xppxp39.node0")
    assert result == "jsessionid=<TOKEN_OR_ID>.node0"

    result = remove_random_identifiers("d32e16a3-1474-4861-a954-cc481b8aa509")
    assert result == "GUID"

    result = remove_random_identifiers(
        "https://region1.google-analytics.com/g/collect?v=2&tid=G-0RSX4L0ZPZ&"
        "gtm=45je47t0v873081270z8832271741za200zb832271741&_p=1722418204159&"
        "gcs=G101&gcd=13q3v3q2q7&npa=1&dma_cps=-&dma=1&tag_exp=95250753&ul=en&"
        "cid=1075964602.1722418205&sr=1280x720&uaa=x86&uab=64&"
        "uafvl=Not%252FA)Brand%3B99.0.0.0%7CHeadlessChrome%3B115.0.5790.75%7"
        "CChromium%3B115.0.5790.75&uamb=0&uam=&uap=Linux&uapv=4.15.0&uaw=0&frm=0"
        "&pscdl=denied&ngs=1&_s=1&sid=1722418205&sct=1&seg=0&dl=https%3A%2F%2F"
        "www.universiteitleiden.nl%2Fen%2Fhumanities%2Finstitute-for-area-studies&"
        "dt=Institute%20for%20Area%20Studies%3A%20Asia%20%26%20the%20Middle%20East%"
        "20-%20Leiden%20University&en=page_view&_fv=1&_nsi=1&_ss=1&ep.faculty_name="
        "Humanities&ep.page_type=organizationlanding&ep.cookies_accepted=false&"
        "up.cookies_geaccepteerd=false&tfd=1730"
    )

    assert result == "https://region1.google-analytics.com/g/collect?<TRACKING_DATA>"
