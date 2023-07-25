import json
from datetime import datetime, timezone

from websecmap.organizations.models import Url
from websecmap.scanners.models import GeoIp, DomainIp, DomainMX, UrlGenericScan, EndpointGenericScan, Endpoint
from websecmap.scanners.scanner.location import (
    scan_mailservers,
    get_geo_ip_database_directly,
    get_domain_to_ip_database_directly,
    get_domain_mx_database_directly,
    get_policy,
    scan_servers, scan_third_party_site_content, SCAN_TYPE_WEBSITE_CONTENT,
)
from websecmap.scanners.scanner.web_privacy import WEB_PRIVACY_THIRD_PARTY_DOMAINS, \
    WEB_PRIVACY_THIRD_PARTY_DOMAINS_NEUTRAL


def test_scan_mailservers(db, default_scan_metadata, default_policy):
    # todo: overwrite some caching functions to make sure test results are unique.
    create_sample_geoip()
    create_sample_domainip()
    create_sample_domainmx()

    Url.objects.create(url="example.com")

    scan_mailservers()

    assert UrlGenericScan.objects.all().count() == 1
    first = UrlGenericScan.objects.all().first()

    # should have a medium continent rating because that is what the software is shipped with.
    assert first.rating == "location_medium"
    assert first.type == "location_mail_server"
    evidence = json.loads(first.evidence)
    assert evidence == [
        {
            "domain": "example.com",
            "evidence": {
                "continent_rating": "medium",
                "country_rating": "ok",
                "found_location": {
                    "as_number": 1337,
                    "as_organization": "test organization",
                    "city_in_en": None,
                    "continent_code": "NA",
                    "country_iso_code": None,
                    "isp_ame": "Test Isp",
                    "network": "10.0.0.0/8",
                },
            },
            "priority": 10,
            "rating": "location_medium",
        },
        {
            "domain": "example.com",
            "evidence": {
                "continent_rating": "unknown",
                "country_rating": "unknown",
                "found_location": {
                    "AS Number": -1,
                    "AS Organization": "",
                    "ISP Name": "",
                    "city": "",
                    "continent": "",
                    "country": "",
                    "network": "",
                },
            },
            "priority": 10,
            "rating": "location_unknown",
        },
    ]


def test_scan_servers(db, default_scan_metadata, default_policy):
    create_sample_geoip()
    create_sample_domainip()

    Url.objects.create(url="example.com")
    scan_servers()

    assert UrlGenericScan.objects.all().count() == 1
    first = UrlGenericScan.objects.all().first()
    assert first.rating == "location_medium"
    assert first.type == "location_server"
    evidence = json.loads(first.evidence)

    # also has an ipv6 address for which we don't have any info, so that will be an unknown
    assert evidence == [
        {
            "domain": "example.com",
            "evidence": {
                "continent_rating": "medium",
                "country_rating": "ok",
                "found_location": {
                    "as_number": 1337,
                    "as_organization": "test organization",
                    "city_in_en": None,
                    "continent_code": "NA",
                    "country_iso_code": None,
                    "isp_ame": "Test Isp",
                    "network": "10.0.0.0/8",
                },
            },
            "rating": "location_medium",
        },
        {
            "domain": "example.com",
            "evidence": {
                "continent_rating": "unknown",
                "country_rating": "unknown",
                "found_location": {
                    "AS Number": -1,
                    "AS Organization": "",
                    "ISP Name": "",
                    "city": "",
                    "continent": "",
                    "country": "",
                    "network": "",
                },
            },
            "rating": "location_unknown",
        },
    ]


def test_scan_third_party_site_content(db):
    create_sample_geoip()
    create_sample_domainip()

    url = Url.objects.create(url="example.com")
    endpoint = Endpoint.objects.create(url=url, port=443, protocol="https", ip_version=4)
    EndpointGenericScan.objects.create(
        endpoint=endpoint,
        type=WEB_PRIVACY_THIRD_PARTY_DOMAINS,
        rating=WEB_PRIVACY_THIRD_PARTY_DOMAINS_NEUTRAL,
        evidence=json.dumps(["example.com"]),
        rating_determined_on=datetime.now(timezone.utc),
        is_the_latest_scan=True
    )

    scan_third_party_site_content()

    # previous scan and the newly derived scan
    assert EndpointGenericScan.objects.all().count() == 2
    first = EndpointGenericScan.objects.all().filter(type=SCAN_TYPE_WEBSITE_CONTENT).first()
    assert first.rating == "location_medium"
    assert first.type == SCAN_TYPE_WEBSITE_CONTENT
    evidence = json.loads(first.evidence)
    assert evidence == [
        {
            "domain": "example.com",
            "evidence": {
                "continent_rating": "medium",
                "country_rating": "ok",
                "found_location": {
                    "as_number": 1337,
                    "as_organization": "test organization",
                    "city_in_en": None,
                    "continent_code": "NA",
                    "country_iso_code": None,
                    "isp_ame": "Test Isp",
                    "network": "10.0.0.0/8",
                },
            },
            "rating": "location_medium",
        },
        {
            "domain": "example.com",
            "evidence": {
                "continent_rating": "unknown",
                "country_rating": "unknown",
                "found_location": {
                    "AS Number": -1,
                    "AS Organization": "",
                    "ISP Name": "",
                    "city": "",
                    "continent": "",
                    "country": "",
                    "network": "",
                },
            },
            "rating": "location_unknown",
        },
    ]


def test_get_policy(db):
    policy = get_policy("mail_server")
    assert policy == {
        "continent_high": ["AS", "AN", "AF", "OC", "SA"],
        "continent_low": [],
        "continent_medium": ["NA"],
        "continent_ok": ["EU"],
        "country_high": ["BE"],
        "country_low": ["DE"],
        "country_medium": ["US"],
        "country_ok": ["NL"],
    }


def create_sample_geoip():
    # get a single record
    GeoIp.objects.create(
        ip_address="8.8.8.8",
        designation="international",
        continent_code="NA",
        continent_in_en="North America",
        isp_country_code="US",
        as_number=1337,
        as_organization="test organization",
        isp_name="Test Isp",
        network="10.0.0.0/8",
        is_the_latest=True,
    )


def create_sample_domainip():
    DomainIp.objects.create(domain="example.com", ip_address="8.8.8.8", ip_version=4, is_the_latest=True)
    DomainIp.objects.create(domain="example.com", ip_address="::1", ip_version=6, is_the_latest=True)


def create_sample_domainmx():
    DomainMX.objects.create(
        domain="example.com",
        mail_server_records=[
            {"priority": 10, "domain": "example.com"},
            {"priority": 20, "domain": "mxin2.amsterdam.nl"},
        ],
        is_the_latest=True,
    )


def test_get_geo_ip_database_directly(db):
    # empty is no exceptions
    db = get_geo_ip_database_directly()
    assert db == {}

    create_sample_geoip()
    db = get_geo_ip_database_directly()
    assert db == {
        "8.8.8.8": {
            "as_number": 1337,
            "as_organization": "test organization",
            "city_in_en": None,
            "continent_code": "NA",
            "country_iso_code": None,
            "ip_address": "8.8.8.8",
            "isp_name": "Test Isp",
            "network": "10.0.0.0/8",
        }
    }


def test_get_domain_to_ip_database_directly(db):
    # empty db means no exceptions
    db = get_domain_to_ip_database_directly()
    assert db == {}

    create_sample_domainip()
    db = get_domain_to_ip_database_directly()
    assert db == {"example.com": {4: "8.8.8.8", 6: "::1"}}


def test_get_domain_mx_database_directly(db):
    db = get_domain_mx_database_directly()
    assert db == {}

    create_sample_domainmx()
    db = get_domain_mx_database_directly()
    assert db == {
        "example.com": [{"domain": "example.com", "priority": 10}, {"domain": "mxin2.amsterdam.nl", "priority": 20}],
    }
