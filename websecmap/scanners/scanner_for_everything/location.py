"""
Rates location based on geographical ip information.

1st iteration is the location of the server

DONE: Harvest mail server IP addresses / MX records
DONE: GeoIP info is returned in ranges, this means we can re-use these ranges to prevent queries. eg: 131.224.250.0/24
DONE: also test website_content

This is based on the following scans, which must all work in order for this to work:
- domain_to_up scanner: which gathers domains from the following scans and gets ip addresses for these domains:
- - MX records, servers and third party website content
- ip_geolocation (geo_ip) scanner for finding what IP address belongs to what location.
- For mail servers: MX records scanner (DomainMX)

You need to run the following periodic tasks:
- websecmap.scanners.scanner_for_everything.mailserver
- websecmap.scanners.scanner_for_everything.ip_geolocation
- - scan_using_known_data daily
- - once every two weeks: create_tasks (and this will run out of credits at some point)
- websecmap.scanners.scanner_for_everything.domain_to_ip
- websecmap.scanners.scanner.web_privacy

This scanner is nothing more than administrative process. Based on the above data in the database results can
be calculated and are added to Url and Endpoint scans.

This results in three different scan types: server, mail_server and third_party_website_content. Each of them
can have the values clean, unknown, ok, low, medium and high.
"""

import contextlib
import json
import logging
from collections import defaultdict
from json import JSONDecodeError
from typing import Any, Dict, List, Tuple

from celery import group

from websecmap.app.constance import constance_cached_value
from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners.models import DomainIp, DomainMX, EndpointGenericScan, GeoIp, UrlGenericScan
from websecmap.scanners.scanmanager import store_endpoint_scan_result, store_url_scan_result
from websecmap.scanners.scanner.metric_constants import (
    WEB_PRIVACY_THIRD_PARTY_DOMAINS,
    WEB_PRIVACY_THIRD_PARTY_DOMAINS_CRAWLED_NO_CONSENT,
    WEB_PRIVACY_THIRD_PARTY_DOMAINS_CRAWLED_WITH_CONSENT,
)

log = logging.getLogger(__name__)

# On URL:
SCAN_TYPE_LOCATION_SERVER = "location_server"
SCAN_TYPE_LOCATION_MAIL_SERVER = "location_mail_server"

# On Endpoint:
SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT = "location_third_party_website_content"
SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT_CRAWL_WITH_CONSENT = (
    "location_third_party_website_content_crawl_with_consent"
)
SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT_CRAWL_WITHOUT_CONSENT = (
    "location_third_party_website_content_crawl_without_consent"
)
SCAN_TYPE_LOCATION_COOKIES = "location_cookies"

LOCATION_HIGH = "location_high"
LOCATION_MEDIUM = "location_medium"
LOCATION_LOW = "location_low"
LOCATION_OK = "location_ok"
LOCATION_UNKNOWN = "location_unknown"

# When there was a location before, but that information has been removed. For example; there where
# mail servers in the past but not any more.
LOCATION_CLEAN = "location_clean"

SUPPORTED_GEOGRAPHY_TYPES = ["server", "mail_server", "website_content"]
SEVERITY_ORDER = [
    "unknown",
    "location_unknown",
    "ok",
    "location_ok",
    "low",
    "location_low",
    "medium",
    "location_medium",
    "high",
    "location_high",
]


def call_with_time_cache(function, cache_key):
    # if cached := time_cache.cache_get(cache_key):
    #     return cached
    answer = function()
    # time_cache.cache_set(cache_key, answer)
    return answer


def get_geoip_database():
    # it's better to load the entire table of latest known stuff instead of re-querying this every time.
    return call_with_time_cache(get_geo_ip_database_directly, "geo-ip-db")


def get_domain_to_ip_database():
    return call_with_time_cache(get_domain_to_ip_database_directly, "domain-ip-db")


def get_domain_mx_database():
    return call_with_time_cache(get_domain_mx_database_directly, "domain-mx")


def get_geo_ip_database_directly():
    # separated for testing purposes
    geoip_db = (
        GeoIp.objects.all()
        .filter(is_the_latest=True)
        .values(
            "ip_address",
            "continent_code",
            "country_iso_code",
            "city_in_en",
            "as_number",
            "as_organization",
            "isp_name",
            "network",
        )
    )
    return {record["ip_address"]: record for record in geoip_db}


def get_domain_to_ip_database_directly():
    """
    data = {
        'example.nl': {
            4: '172.16.17.32',
            6: '::1'
        }
        ...
    }
    """
    records = DomainIp.objects.all().filter(is_the_latest=True).values("domain", "ip_address", "ip_version")

    data = defaultdict(dict)
    for record in records:
        data[record["domain"]][record["ip_version"]] = record["ip_address"]

    return data


def get_domain_mx_database_directly():
    records = DomainMX.objects.all().filter(is_the_latest=True).values("domain", "mail_server_records")
    return {record["domain"]: record["mail_server_records"] for record in records}


@app.task(queue="kickoff")
def create_tasks() -> group:
    # This largely depends on the accuracy and up-to-date-ness of the geo-ip database and the resolving of the
    # ip addresses, which are separate tasks that are run daily.
    # Todo: make sure these scans are scheduled in logical order.
    return group([scan_servers.si() | scan_mailservers.si() | scan_third_party_site_content.si()])


@app.task(queue="database", ignore_result=True)
def scan_mailservers():
    # there can be many mailservers configured. Each of them has to comply.
    # MX is just a bunch of domains, which is the same check as a webserver scan, but multiple times.
    # both v4 and v6 have to comply if used. So for a single address like tweakers.net this results in 8 checks.
    # the worst of them determines the final result.
    # this seems to be an url-level scan. as an endpoint cannot have mailservers (it can be a mailserver domain).
    geo_ip_data = get_geoip_database()
    domain_ip_data = get_domain_to_ip_database()
    domain_mx_data = get_domain_mx_database()

    urls = Url.objects.all().filter(is_dead=False, not_resolvable=False).only("id", "url")

    for url in urls:
        mail_servers = domain_mx_data.get(url.url, [])
        if not mail_servers:
            # clean up existing record: Most addresses don't have mail servers anyway but each
            # one can have a different one and some of them might be removed.
            existing_scan = (
                UrlGenericScan.objects.all()
                .filter(type=SCAN_TYPE_LOCATION_MAIL_SERVER, url_id=url.id, is_the_latest_scan=True)
                .first()
            )
            if existing_scan and existing_scan.rating != LOCATION_CLEAN:
                store_url_scan_result(
                    scan_type=SCAN_TYPE_LOCATION_MAIL_SERVER,
                    url_id=url.id,
                    rating=LOCATION_CLEAN,
                    message=LOCATION_CLEAN,
                    evidence=json.dumps([]),
                )

            # don't further process this url
            continue

        worst_rating, rating_series = create_rating_series_for_domains(mail_servers, domain_ip_data, geo_ip_data)

        store_url_scan_result(
            scan_type=SCAN_TYPE_LOCATION_MAIL_SERVER,
            url_id=url.id,
            rating=worst_rating,
            message=worst_rating,
            evidence=json.dumps(rating_series),
        )


@app.task(queue="database", ignore_result=True)
def scan_servers():
    # basically every server that is resolvable will get a metric, so you don't need to remove findings.
    geo_ip_data = get_geoip_database()
    domain_ip_data = get_domain_to_ip_database()

    urls = Url.objects.all().filter(is_dead=False, not_resolvable=False).only("id", "url")
    for url in urls:
        worst_rating, rating_series = create_rating_series_for_domains(
            [{"domain": url.url}], domain_ip_data, geo_ip_data
        )
        store_url_scan_result(
            scan_type=SCAN_TYPE_LOCATION_SERVER,
            url_id=url.id,
            rating=worst_rating,
            message=worst_rating,
            evidence=json.dumps(rating_series),
        )


@app.task(queue="database", ignore_result=True)
def scan_third_party_site_content():
    # this is just the front page
    scan_third_party_site_content_abs(WEB_PRIVACY_THIRD_PARTY_DOMAINS, SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT)

    # also do this with all resources from the site
    scan_third_party_site_content_abs(
        WEB_PRIVACY_THIRD_PARTY_DOMAINS_CRAWLED_WITH_CONSENT,
        SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT_CRAWL_WITH_CONSENT,
    )
    scan_third_party_site_content_abs(
        WEB_PRIVACY_THIRD_PARTY_DOMAINS_CRAWLED_NO_CONSENT,
        SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT_CRAWL_WITHOUT_CONSENT,
    )


def scan_third_party_site_content_abs(
    from_type: str = WEB_PRIVACY_THIRD_PARTY_DOMAINS, to_type: str = SCAN_TYPE_LOCATION_THIRD_PARTY_WEBSITE_CONTENT
):
    geo_ip_data = get_geoip_database()
    domain_ip_data = get_domain_to_ip_database()
    epgss = (
        EndpointGenericScan.objects.all()
        .filter(type=from_type, is_the_latest_scan=True)
        .only("endpoint_id", "evidence")
    )
    log.debug("Found %d endpoints with site content", epgss.count())

    for epgs in epgss:
        # There will always be site content, if not the list will be empty and thus this metric also.
        # No need to clean this up.
        with contextlib.suppress(JSONDecodeError):
            evidence_domains = json.loads(epgs.evidence)
            domains = [{"domain": domain} for domain in evidence_domains]
            worst_rating, rating_series = create_rating_series_for_domains(domains, domain_ip_data, geo_ip_data)
            store_endpoint_scan_result(
                scan_type=to_type,
                endpoint_id=epgs.endpoint.id,
                rating=worst_rating,
                message=worst_rating,
                evidence=json.dumps(rating_series),
            )


def meaning_of_location_at_web_privacy_cookies(cookies, domain_ip_data=None, geo_ip_data=None):
    # you can give them in advance so to save this call which returns a lot of data
    if not domain_ip_data:
        domain_ip_data = get_domain_to_ip_database()
    if not geo_ip_data:
        geo_ip_data = get_geoip_database()

    domains = [
        {"domain": domain, "applicable_cookies": applicable_cookies(domain, cookies)}
        for domain in extract_domains_from_cookies(cookies)
    ]
    worst_rating, rating_series = create_rating_series_for_domains(domains, domain_ip_data, geo_ip_data)

    return worst_rating, rating_series


def applicable_cookies(domain: str, cookies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [cookie for cookie in cookies if cookie["domain"] in [domain, f".{domain}"]] if cookies else []


def extract_domains_from_cookies(cookies: List[Dict[str, Any]]) -> List[str]:
    """
    Extracts domains from a list of cookies.
    """
    if not cookies:
        return []

    domains = set()
    for cookie in cookies:
        if domain := cookie.get("domain", None):
            if domain.startswith("."):
                domain = domain[1:]

            domains.add(domain)
    # constant ordering so values stay in the same order always
    return list(sorted(domains))


def create_rating_series_for_domains(domains: List[Dict[str, Any]], domain_ip_database, geo_ip_database):
    # domains list contains "domain" and optionally "priority" for mailservers
    # eg: [{'domain': 'example.com', 'priority': 'high'}, {'domain': 'test.nl'}]...
    rating_series = []
    include_ipv6 = constance_cached_value("GEOGRAPHY_RATINGS_INCLUDE_IPV6")
    for mail_server in domains:
        ips = []
        if ipv4 := domain_ip_database.get(mail_server["domain"], {}).get(4, None):
            ips.append(ipv4)
        if include_ipv6:
            if ipv6 := domain_ip_database.get(mail_server["domain"], {}).get(6, None):
                ips.append(ipv6)

        for ip in ips:
            overall_rating, evidence = match_ip_up_to_policy(ip, "mail_server", geo_ip_database)
            rating = {"rating": overall_rating, "evidence": evidence, "domain": mail_server["domain"]}
            # inject some properties if those are in the list of domains, should by any other value
            if "priority" in mail_server:
                rating["priority"] = mail_server["priority"]
            if "applicable_cookies" in mail_server:
                rating["applicable_cookies"] = mail_server["applicable_cookies"]
            rating_series.append(rating)

    # get the worst from the rating series and use that as the final verdict. The Whole rating series
    # is used as evidence.
    # The worst between country and continent has already been figured out in the overall rating
    current_worst_rating = LOCATION_UNKNOWN
    for rating in rating_series:
        if SEVERITY_ORDER.index(rating["rating"]) > SEVERITY_ORDER.index(current_worst_rating):
            current_worst_rating = rating["rating"]

    return current_worst_rating, rating_series


def match_ip_up_to_policy(
    ip_address, geopgraphy_type: str = "server", geo_ip_database=None
) -> Tuple[str, Dict[str, Any]]:
    if ip_address not in geo_ip_database:
        return LOCATION_UNKNOWN, {
            "found_location": {
                "continent": "",
                "country": "",
                "city": "",
                "AS Number": -1,
                "AS Organization": "",
                "ISP Name": "",
                "network": "",
            },
            "country_rating": "unknown",
            "continent_rating": "unknown",
        }

    policy = get_policy(geopgraphy_type)
    geo_ip_record = geo_ip_database[ip_address]

    rating = rate(geo_ip_record, policy)

    evidence = {
        "found_location": {
            "continent_code": geo_ip_record.get("continent_code", ""),
            "country_iso_code": geo_ip_record.get("country_iso_code", ""),
            "city_in_en": geo_ip_record.get("city_in_en", ""),
            "as_number": geo_ip_record.get("as_number", ""),
            "as_organization": geo_ip_record.get("as_organization", ""),
            "isp_ame": geo_ip_record.get("isp_name", ""),
            "network": geo_ip_record.get("network", ""),
        },
        "country_rating": rating.get("country_rating", LOCATION_UNKNOWN).replace("location_", ""),
        "continent_rating": rating.get("continent_rating", LOCATION_UNKNOWN).replace("location_", ""),
    }

    return rating.get("overall_rating", LOCATION_UNKNOWN), evidence


def rate(geo_ip_record: dict, policy: dict):
    continent_rating = _extracted_from_rate_3(geo_ip_record, "continent_code", "continent", policy)
    country_rating = _extracted_from_rate_3(geo_ip_record, "country_iso_code", "country", policy)

    # country rating is more specific and thus more important than continent rating.
    # if the country rating is something more specific than unknown, than the country rating
    # always takes preference. 0 + 1 are unknown, many countries will be unknown while the
    # continent will be filled.
    if SEVERITY_ORDER.index(country_rating) > 1:
        overall_rating = country_rating
    else:
        overall_rating = continent_rating

    return {"continent_rating": continent_rating, "country_rating": country_rating, "overall_rating": overall_rating}


# TODO Rename this here and in `rate`
def _extracted_from_rate_3(geo_ip_record, arg1, c_or_c, policy):
    found_code = geo_ip_record.get(arg1, "")
    if found_code in policy[f"{c_or_c}_high"]:
        return LOCATION_HIGH
    if found_code in policy[f"{c_or_c}_low"]:
        return LOCATION_LOW
    if found_code in policy[f"{c_or_c}_medium"]:
        return LOCATION_MEDIUM
    if found_code in policy[f"{c_or_c}_ok"]:
        return LOCATION_OK
    return LOCATION_UNKNOWN


def get_policy(geography_type: str = "server"):
    if geography_type not in SUPPORTED_GEOGRAPHY_TYPES:
        raise ValueError(f"content_type must be one of {SUPPORTED_GEOGRAPHY_TYPES}, got {geography_type}")

    keys = {}
    if geography_type == "mail_server":
        keys = {
            "continent_ok": "GEOGRAPHY_EMAIL_SERVER_IN_CONTINENT_OK",
            "continent_low": "GEOGRAPHY_EMAIL_SERVER_IN_CONTINENT_LOW",
            "continent_medium": "GEOGRAPHY_EMAIL_SERVER_IN_CONTINENT_MEDIUM",
            "continent_high": "GEOGRAPHY_EMAIL_SERVER_IN_CONTINENT_HIGH",
            "country_ok": "GEOGRAPHY_EMAIL_SERVER_IN_COUNTRIES_OK",
            "country_low": "GEOGRAPHY_EMAIL_SERVER_IN_COUNTRIES_LOW",
            "country_medium": "GEOGRAPHY_EMAIL_SERVER_IN_COUNTRIES_MEDIUM",
            "country_high": "GEOGRAPHY_EMAIL_SERVER_IN_COUNTRIES_HIGH",
        }

    elif geography_type == "server":
        keys = {
            "continent_ok": "GEOGRAPHY_SERVER_IN_CONTINENT_OK",
            "continent_low": "GEOGRAPHY_SERVER_IN_CONTINENT_LOW",
            "continent_medium": "GEOGRAPHY_SERVER_IN_CONTINENT_MEDIUM",
            "continent_high": "GEOGRAPHY_SERVER_IN_CONTINENT_HIGH",
            "country_ok": "GEOGRAPHY_SERVER_IN_COUNTRIES_OK",
            "country_low": "GEOGRAPHY_SERVER_IN_COUNTRIES_LOW",
            "country_medium": "GEOGRAPHY_SERVER_IN_COUNTRIES_MEDIUM",
            "country_high": "GEOGRAPHY_SERVER_IN_COUNTRIES_HIGH",
        }
    elif geography_type == "website_content":
        keys = {
            "continent_ok": "GEOGRAPHY_WEBSITE_THIRD_PARTY_CONTENT_FROM_CONTINENT_OK",
            "continent_low": "GEOGRAPHY_WEBSITE_THIRD_PARTY_CONTENT_FROM_CONTINENT_LOW",
            "continent_medium": "GEOGRAPHY_WEBSITE_THIRD_PARTY_CONTENT_FROM_CONTINENT_MEDIUM",
            "continent_high": "GEOGRAPHY_WEBSITE_THIRD_PARTY_CONTENT_FROM_CONTINENT_HIGH",
            "country_ok": "GEOGRAPHY_WEBSITE_THIRD_PARTY_CONTENT_FROM_COUNTRIES_OK",
            "country_low": "GEOGRAPHY_WEBSITE_THIRD_PARTY_CONTENT_FROM_COUNTRIES_LOW",
            "country_medium": "GEOGRAPHY_WEBSITE_THIRD_PARTY_CONTENT_FROM_COUNTRIES_MEDIUM",
            "country_high": "GEOGRAPHY_WEBSITE_THIRD_PARTY_CONTENT_FROM_COUNTRIES_HIGH",
        }

    # to prevent highlighting a not defined issue:
    if not keys:
        raise ValueError(f"Keys empty! {SUPPORTED_GEOGRAPHY_TYPES}, got {geography_type}")

    return {
        "continent_ok": json.loads(constance_cached_value(keys["continent_ok"])),
        "continent_low": json.loads(constance_cached_value(keys["continent_low"])),
        "continent_medium": json.loads(constance_cached_value(keys["continent_medium"])),
        "continent_high": json.loads(constance_cached_value(keys["continent_high"])),
        "country_ok": json.loads(constance_cached_value(keys["country_ok"])),
        "country_low": json.loads(constance_cached_value(keys["country_low"])),
        "country_medium": json.loads(constance_cached_value(keys["country_medium"])),
        "country_high": json.loads(constance_cached_value(keys["country_high"])),
    }
