from datetime import timezone, datetime
import json

from websecmap.scanners.cleaners import clean_http_security_header_strict_transport_security, something_something_hsts
from websecmap.scanners.duplicates import deduplicate_all_scans_sequentially, deduplicate_all_endpoints_sequentially
from websecmap.scanners.models import EndpointGenericScan, Endpoint
from websecmap.scanners.tests.test_plannedscan import create_endpoint, create_url


def test_clean_http_security_header_strict_transport_security(db):
    # we're creating a bunch of hsts scans on various endpoints. When cleaning them all of these scans
    # will turn out to be exactly the same. Then we'll check if these scans can be merged into one
    # and then all endpoints on this url will be deduplicated.

    u = create_url("example.nl")
    e1 = create_endpoint(u, 4, "https", 443)
    e1.discovered_on = datetime(2020, 1, 1, tzinfo=timezone.utc)
    e1.save()
    e2 = create_endpoint(u, 4, "https", 443)
    e2.discovered_on = datetime(2021, 1, 1, tzinfo=timezone.utc)
    e2.save()
    e3 = create_endpoint(u, 4, "https", 443)
    e3.discovered_on = datetime(2022, 1, 1, tzinfo=timezone.utc)
    e3.save()

    evidence = [
        {
            "request": 1,
            "url": "https://mijn.preprod1.digid.nl:443/",
            "protocol": "https",
            "status_code": 302,
            "content_type": "text/html; charset=utf-8",
            "headers": {
                "content-security-policy": "default-src 'self'; base-uri 'self'; font-src 'self' data:; img-src 'self'",
                "content-type": "text/html; charset=utf-8",
                "location": "https://preprod1.digid.nl/?check_cookie=true&process=my_digid&url=https%3a%2f%2fmijn.pre",
                "permissions-policy": "accelerometer=(), ambient-light-sensor=(), autoplay=(), battery=(), camera=(),",
                "referrer-policy": "same-origin",
                "strict-transport-security": "max-age=31536000 ; includesubdomains",
                "x-content-type-options": "nosniff",
                "x-frame-options": "sameorigin",
                "x-xss-protection": "1; mode=block",
            },
        },
        {
            "request": 2,
            "url": "https://preprod1.digid.nl/?check_cookie=true&process=my_digid&url=https%3A%2F%2Fmijn.preprod1.dig",
            "protocol": "https",
            "status_code": 302,
            "content_type": "text/html; charset=utf-8",
            "headers": {
                "content-security-policy": "default-src 'self'; base-uri 'self'; font-src 'self' data:; img-src 'self",
                "content-type": "text/html; charset=utf-8",
                "location": "https://preprod1.digid.nl/cookies_geblokkeerd?process=my_digid&url=https%3a%2f%2fmijn.pr",
                "permissions-policy": "accelerometer=(), ambient-light-sensor=(), autoplay=(), battery=(), camera=(),",
                "referrer-policy": "same-origin",
                "strict-transport-security": "max-age=31536000 ; includesubdomains",
                "x-content-type-options": "nosniff",
                "x-frame-options": "sameorigin",
                "x-xss-protection": "1; mode=block",
            },
        },
    ]

    # some scan on endpoint 1 and 2, add some extra value to see if everything is reduced correctly and only
    # one scan remains
    evidence[0]["headers"]["new_value"] = "test1"
    epgs1 = EndpointGenericScan()
    epgs1.endpoint = e1
    epgs1.rating = "present"
    epgs1.last_scan_moment = datetime(2020, 1, 5, tzinfo=timezone.utc)
    epgs1.type = "http_security_header_strict_transport_security"
    epgs1.rating_determined_on = datetime(2020, 1, 5, tzinfo=timezone.utc)
    epgs1.evidence = json.dumps(evidence)
    epgs1.save()

    evidence[0]["headers"]["new_value"] = "test2"
    epgs2 = EndpointGenericScan()
    epgs2.endpoint = e2
    epgs2.rating = "present"
    epgs2.last_scan_moment = datetime(2020, 1, 5, tzinfo=timezone.utc)
    epgs2.type = "http_security_header_strict_transport_security"
    epgs2.rating_determined_on = datetime(2020, 1, 5, tzinfo=timezone.utc)
    epgs2.evidence = json.dumps(evidence)
    epgs2.save()

    # earlier scan on endpoint 1 and 2
    evidence[0]["headers"]["new_value"] = "test3"
    epgs3 = EndpointGenericScan()
    epgs3.endpoint = e1
    epgs3.rating = "present"
    epgs3.last_scan_moment = datetime(2019, 1, 5, tzinfo=timezone.utc)
    epgs3.type = "http_security_header_strict_transport_security"
    epgs3.rating_determined_on = datetime(2019, 1, 5, tzinfo=timezone.utc)
    epgs3.evidence = json.dumps(evidence)
    epgs3.save()

    evidence[0]["headers"]["new_value"] = "test4"
    epgs4 = EndpointGenericScan()
    epgs4.endpoint = e2
    epgs4.rating = "present"
    epgs4.last_scan_moment = datetime(2019, 1, 5, tzinfo=timezone.utc)
    epgs4.type = "http_security_header_strict_transport_security"
    epgs4.rating_determined_on = datetime(2019, 1, 5, tzinfo=timezone.utc)
    epgs4.evidence = json.dumps(evidence)
    epgs4.save()

    # some scan on endpoint 3
    evidence[0]["headers"]["new_value"] = "test5"
    epgs5 = EndpointGenericScan()
    epgs5.endpoint = e3
    epgs5.rating = "present"
    epgs5.last_scan_moment = datetime(2016, 1, 5, tzinfo=timezone.utc)
    epgs5.type = "http_security_header_strict_transport_security"
    epgs5.rating_determined_on = datetime(2019, 1, 5, tzinfo=timezone.utc)
    epgs5.evidence = json.dumps(evidence)
    epgs5.save()

    # reduce scan data
    clean_http_security_header_strict_transport_security()

    # above parallelization doesn't work during tests...
    something_something_hsts(epgs1.id)
    something_something_hsts(epgs2.id)
    something_something_hsts(epgs3.id)
    something_something_hsts(epgs4.id)
    something_something_hsts(epgs5.id)

    # now dedupe, and only one thing should have remained
    deduplicate_all_endpoints_sequentially(days=600)
    deduplicate_all_scans_sequentially()

    # deduplicate_all_scans_sequentially()
    # deduplicate_all_endpoints_sequentially(days=600)

    # all endpoints have been merged into one
    assert Endpoint.objects.all().count() == 1

    # all scans should have been the same now
    assert EndpointGenericScan.objects.count() == 1

    # evidence should be reduced and it should all be the same
    data = EndpointGenericScan.objects.all().first().evidence
    assert json.loads(data) == [
        {
            "content_type": "text/html; charset=utf-8",
            "headers": {
                "location": "https://preprod1.digid.nl/",
                "strict-transport-security": "max-age=31536000 ; " "includesubdomains",
            },
            "protocol": "https",
            "request": 1,
            "status_code": 302,
            "url": "https://mijn.preprod1.digid.nl:443/",
        },
        {
            "content_type": "text/html; charset=utf-8",
            "headers": {
                "location": "https://preprod1.digid.nl/cookies_geblokkeerd",
                "strict-transport-security": "max-age=31536000 ; " "includesubdomains",
            },
            "protocol": "https",
            "request": 2,
            "status_code": 302,
            "url": "https://preprod1.digid.nl/",
        },
    ]


def test_something_something_hsts(db):
    u = create_url("example.nl")
    e1 = create_endpoint(u, 4, "https", 443)
    e1.discovered_on = datetime(2020, 1, 1, tzinfo=timezone.utc)
    e1.save()

    evidence = [
        {
            "request": 1,
            "url": "https://mijn.preprod1.digid.nl:443/",
            "protocol": "https",
            "status_code": 302,
            "content_type": "text/html; charset=utf-8",
            "headers": {
                "content-security-policy": "default-src 'self'; base-uri 'self'; font-src 'self' data:; img-src 'self'",
                "content-type": "text/html; charset=utf-8",
                "location": "https://preprod1.digid.nl/?check_cookie=true&process=my_digid&url=https%3a%2f%2fmijn.pre",
                "permissions-policy": "accelerometer=(), ambient-light-sensor=(), autoplay=(), battery=(), camera=(),",
                "referrer-policy": "same-origin",
                "strict-transport-security": "max-age=31536000 ; includesubdomains",
                "x-content-type-options": "nosniff",
                "x-frame-options": "sameorigin",
                "x-xss-protection": "1; mode=block",
            },
        },
        {
            "request": 2,
            "url": "https://preprod1.digid.nl/?check_cookie=true&process=my_digid&url=https%3A%2F%2Fmijn.preprod1.dig",
            "protocol": "https",
            "status_code": 302,
            "content_type": "text/html; charset=utf-8",
            "headers": {
                "content-security-policy": "default-src 'self'; base-uri 'self'; font-src 'self' data:; img-src 'self",
                "content-type": "text/html; charset=utf-8",
                "location": "https://preprod1.digid.nl/cookies_geblokkeerd?process=my_digid&url=https%3a%2f%2fmijn.pr",
                "permissions-policy": "accelerometer=(), ambient-light-sensor=(), autoplay=(), battery=(), camera=(),",
                "referrer-policy": "same-origin",
                "strict-transport-security": "max-age=31536000 ; includesubdomains",
                "x-content-type-options": "nosniff",
                "x-frame-options": "sameorigin",
                "x-xss-protection": "1; mode=block",
            },
        },
    ]

    epgs1 = EndpointGenericScan()
    epgs1.endpoint = e1
    epgs1.rating = "present"
    epgs1.last_scan_moment = datetime(2020, 1, 5, tzinfo=timezone.utc)
    epgs1.type = "http_security_header_strict_transport_security"
    epgs1.rating_determined_on = datetime(2020, 1, 5, tzinfo=timezone.utc)
    epgs1.evidence = json.dumps(evidence)
    epgs1.save()

    something_something_hsts(epgs1.id)

    new_epgs = EndpointGenericScan.objects.get(id=epgs1.id)
    assert json.loads(new_epgs.evidence) == [
        {
            "request": 1,
            "url": "https://mijn.preprod1.digid.nl:443/",
            "protocol": "https",
            "status_code": 302,
            "content_type": "text/html; charset=utf-8",
            "headers": {
                "strict-transport-security": "max-age=31536000 ; includesubdomains",
                "location": "https://preprod1.digid.nl/",
            },
        },
        {
            "request": 2,
            "url": "https://preprod1.digid.nl/",
            "protocol": "https",
            "status_code": 302,
            "content_type": "text/html; charset=utf-8",
            "headers": {
                "strict-transport-security": "max-age=31536000 ; includesubdomains",
                "location": "https://preprod1.digid.nl/cookies_geblokkeerd",
            },
        },
    ]
