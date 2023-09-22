import json
from datetime import datetime, timezone

from websecmap.organizations.models import Url
from websecmap.scanners.models import GeoIp, DomainIp, DomainMX, UrlGenericScan, EndpointGenericScan, Endpoint
from websecmap.scanners.scanner_for_everything.location import (
    scan_mailservers,
    get_geo_ip_database_directly,
    get_domain_to_ip_database_directly,
    get_domain_mx_database_directly,
    get_policy,
    scan_servers,
    scan_third_party_site_content,
    SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT,
    create_meaning_of_location_at_web_privacy_cookies,
    extract_domains_from_cookies,
    SCAN_TYPE_LOCATION_COOKIES,
)
from websecmap.scanners.scanner.web_privacy import (
    WEB_PRIVACY_THIRD_PARTY_DOMAINS,
    WEB_PRIVACY_THIRD_PARTY_DOMAINS_NEUTRAL,
    WEB_PRIVACY_COOKIES,
    WEB_PRIVACY_COOKIES_NEUTRAL,
)
from constance.test import override_config


@override_config(GEOGRAPHY_RATINGS_INCLUDE_IPV6=True)
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
                "country_rating": "unknown",
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


@override_config(GEOGRAPHY_RATINGS_INCLUDE_IPV6=True)
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
                "country_rating": "unknown",
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


@override_config(GEOGRAPHY_RATINGS_INCLUDE_IPV6=True)
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
        is_the_latest_scan=True,
    )

    scan_third_party_site_content()

    # previous scan and the newly derived scan
    assert EndpointGenericScan.objects.all().count() == 2
    first = EndpointGenericScan.objects.all().filter(type=SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT).first()
    assert first.rating == "location_medium"
    assert first.type == SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT
    evidence = json.loads(first.evidence)
    assert evidence == [
        {
            "domain": "example.com",
            "evidence": {
                "continent_rating": "medium",
                "country_rating": "unknown",
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


@override_config(GEOGRAPHY_RATINGS_INCLUDE_IPV6=True)
def test_create_meaning_of_location_at_web_privacy_cookies(db):
    create_sample_geoip()
    create_sample_domainip()

    url = Url.objects.create(url="example.com")
    endpoint = Endpoint.objects.create(url=url, port=443, protocol="https", ip_version=4)
    EndpointGenericScan.objects.create(
        endpoint=endpoint,
        type=WEB_PRIVACY_COOKIES,
        rating=WEB_PRIVACY_COOKIES_NEUTRAL,
        evidence=json.dumps(
            [
                {"name": "__utma", "domain": ".example.com", "sameSite": "Lax"},
                {"name": "__utmb", "domain": ".example.com", "sameSite": "Lax"},
                {"name": "__utmc", "domain": ".example.com", "sameSite": "Lax"},
                {"name": "__utmt", "domain": ".example.com", "sameSite": "Lax"},
                {"name": "__utmz", "domain": ".example.com", "sameSite": "Lax"},
                {"name": "_ga", "domain": ".example.com", "path": "/", "sameSite": "Lax"},
                {"name": "_ga_SPWNB9HS5Y", "domain": ".example.com", "secure": False, "sameSite": "Lax"},
                {"name": "_pk_id.1.961b", "domain": "www.example.com", "path": "/", "sameSite": "Lax"},
                {
                    "name": "_pk_ses.1.961b",
                    "domain": "www.example.com",
                    "path": "/",
                    "httpOnly": False,
                },
            ]
        ),
        rating_determined_on=datetime.now(timezone.utc),
        is_the_latest_scan=True,
    )

    create_meaning_of_location_at_web_privacy_cookies()

    epgs = EndpointGenericScan.objects.filter(type=WEB_PRIVACY_COOKIES).first()
    assert "locations" in epgs.meaning
    assert epgs.meaning["locations"] == [
        {
            "domain": "example.com",
            "evidence": {
                "continent_rating": "medium",
                "country_rating": "unknown",
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
    assert epgs.meaning["locations_worst_rating"] == "location_medium"

    # an additional scan was created, and the above endpoint received some meaning
    assert EndpointGenericScan.objects.count() == 2
    epgs = EndpointGenericScan.objects.filter(type=SCAN_TYPE_LOCATION_COOKIES).first()
    assert epgs.rating == "location_medium"
    assert epgs


def test_extract_domains_from_cookies():
    # omit some fields so it fits in a single line for readability
    kex = [
        {"name": "__utma", "domain": ".hardenberg.nl", "sameSite": "Lax"},
        {"name": "__utmb", "domain": ".hardenberg.nl", "sameSite": "Lax"},
        {"name": "__utmc", "domain": ".hardenberg.nl", "sameSite": "Lax"},
        {"name": "__utmt", "domain": ".hardenberg.nl", "sameSite": "Lax"},
        {"name": "__utmz", "domain": ".hardenberg.nl", "sameSite": "Lax"},
        {"name": "_ga", "domain": ".hardenberg.nl", "path": "/", "sameSite": "Lax"},
        {"name": "_ga_SPWNB9HS5Y", "domain": ".hardenberg.nl", "secure": False, "sameSite": "Lax"},
        {"name": "_pk_id.1.961b", "domain": "www.hardenberg.nl", "path": "/", "sameSite": "Lax"},
        {
            "name": "_pk_ses.1.961b",
            "domain": "www.hardenberg.nl",
            "path": "/",
            "httpOnly": False,
        },
    ]

    assert extract_domains_from_cookies(kex) == ["hardenberg.nl", "www.hardenberg.nl"]

    # some more scenarios
    kekz = [
        {"name": "__utma", "domain": ".hardenberg.nl", "sameSite": "Lax"},
        {"name": "__utma", "domain": ".nu.nl", "sameSite": "Lax"},
        {"name": "__utma", "domain": ".internetcleanup.foundation", "sameSite": "Lax"},
    ]
    assert extract_domains_from_cookies(kekz) == [
        "hardenberg.nl",
        "internetcleanup.foundation",
        "nu.nl",
    ]

    assert extract_domains_from_cookies([]) == []
