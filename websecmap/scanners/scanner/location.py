"""
Rates location based on geographical ip information.

1st iteration is the location of the server

Todo: Harvest mail server IP addresses / MX records
Todo: GeoIP info is returned in ranges, this means we can re-use these ranges to prevent queries. eg: 131.224.250.0/24
Todo: also test website_content
"""
import json

from collections import defaultdict
from typing import Any, Dict, Tuple

from websecmap.app.constance import constance_cached_value
from websecmap.organizations.models import Url
from websecmap.reporting import time_cache
from websecmap.scanners.models import GeoIp, Endpoint, DomainIp, DomainMX
from websecmap.scanners.scanmanager import store_endpoint_scan_result, store_url_scan_result

SCAN_TYPE_WEB_SERVER = "location_web_server"
SCAN_TYPE_MAIL_SERVER = "location_mail_server"
SCAN_TYPE_WEBSITE_CONTENT = "location_website_content"

LOCATION_HIGH = "location_high"
LOCATION_MEDIUM = "location_medium"
LOCATION_LOW = "location_low"
LOCATION_OK = "location_ok"
LOCATION_UNKNOWN = "location_unknown"

SUPPORTED_GEOGRAPHY_TYPES = ['web_server', 'mail_server', 'website_content']
SEVERITY_ORDER = ["unknown", "ok", "low", "medium", "high"]


def call_with_time_cache(function, cache_key):
    if cached := time_cache.cache_get(cache_key):
        return cached
    answer = function()
    time_cache.cache_set(cache_key, answer)
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
    geoip_db = GeoIp.objects.all().filter(
        is_the_latest=True
    ).values(
        'ip_address',
        'continent_code',
        'country_iso_code',
        'city_in_en',
        'as_number',
        'as_organization',
        'isp_name',
        'network'
    )
    return {record['ip_address']: record for record in geoip_db}


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
    records = DomainIp.objects.all().filter(
        is_the_latest=True
    ).values(
        'domain'
        'ip_address'
        'ip_version'
    )

    data = defaultdict(dict)
    for record in records:
        data[record['domain']][record['ip_version']] = record['ip_address']

    return data


def get_domain_mx_database_directly():
    records = DomainMX.objects.all().filter(
        is_the_latest=True
    ).values(
        'domain',
        'mail_server_records'
    )
    return {record['domain']: record['mail_server_records'] for record in records}


def scan():
    ...
    scan_webservers()
    scan_mailservers()


def scan_mailservers():
    # there can be many mailservers configured. Each of them has to comply.
    # MX is just a bunch of domains, which is the same check as a webserver scan, but multiple times.
    # both v4 and v6 have to comply if used. So for a single address like tweakers.net this results in 8 checks.
    # the worst of them determines the final result.
    # this seems to be an url-level scan. as an endpoint cannot have mailservers (it can be a mailserver domain).
    geo_ip_data = get_geoip_database()
    domain_ip_data = get_domain_to_ip_database()
    domain_mx_data = get_domain_mx_database()

    urls = Url.objects.all().filter(
        is_dead=False,
        not_registered=False
    )

    # todo: this logic is the same for content of webpages: multiple ip's, multiple checks. But you want to
    # show the priority of the server in the evidence to be complete.
    for url in urls:
        mail_servers = domain_mx_data.get(url.url, [])
        if not mail_servers:
            # todo: clean up existing record if need be. Most addresses don't have mail servers anyway but each
            # one can have a different one.
            continue

        rating_series = []
        for mail_server in mail_servers:
            ips = []
            if ipv4 := domain_ip_data.get(mail_server['domain'], {}).get(4, None):
                ips.append(ipv4)
            if ipv6 := domain_ip_data.get(mail_server['domain'], {}).get(6, None):
                ips.append(ipv6)

            for ip in ips:
                rating, evidence = match_ip_up_to_policy(ip, "mail_server", geo_ip_data)
                rating_series.append({'rating': rating, 'evidence': evidence,
                                      'domain': mail_server['domain'], 'priority': mail_server['priority']})

        # get the worst from the rating series and use that as the final verdict. The Whole rating series
        # is used as evidence.
        # The worst between country and continent has already been figured out in the overall rating
        current_worst_rating = LOCATION_UNKNOWN
        for rating in rating_series:
            if SEVERITY_ORDER.index(rating['overall_rating']) >  SEVERITY_ORDER.index(current_worst_rating):
                current_worst_rating = rating['overall_rating']

        store_url_scan_result(
            scan_type=SCAN_TYPE_MAIL_SERVER,
            url_id=url.id,
            rating=current_worst_rating,
            message=current_worst_rating,
            evidence=json.dumps(rating_series),
        )


def scan_webservers():
    # webserver endpoints, not e-mail or content.
    # webserver endpoints can be v4 and v6.
    geo_ip_data = get_geoip_database()

    # A and AAAA records, no MX records here...
    domain_ip_data = get_domain_to_ip_database()

    eps = Endpoint.objects.all().filter(
        is_dead=False,
        url__is_dead=False,
        url__not_resolvable=False,
        protocol__in=["http", "https"]
    )

    # todo: how to deal with ip's that have disappeared etc? Should we only add if something is useful here and
    # set it to nothing when there was a previous record?
    for ep in eps:
        # get current IP for this address
        ip = domain_ip_data.get(ep.url.url, {}).get(ep.ip_version, None)
        rating, evidence = match_ip_up_to_policy(ip, "web_server", geo_ip_data)
        store_endpoint_scan_result(
            scan_type=SCAN_TYPE_WEB_SERVER,
            endpoint_id=ep.id,
            rating=rating,
            message=rating,
            evidence=json.dumps(evidence),
        )


def match_ip_up_to_policy(
    ip_address, geopgraphy_type: str = 'web_server', geo_ip_database=None
) -> Tuple[str, Dict[str, Any]]:

    if ip_address not in geo_ip_database:
        return LOCATION_UNKNOWN, {
            'found_location': {
                'continent': '',
                'country': '',
                'city': "",
                'AS Number': -1,
                'AS Organization': '',
                'ISP Name': '',
                'network': '',
            },
            'country_rating': "unknown",
            'continent_rating': "unknown",
        }

    policy = get_policy(geopgraphy_type)
    geo_ip_record = geo_ip_database[ip_address]

    rating = rate(geo_ip_record, policy)

    evidence = {
        'found_location': {
            'continent_code': geo_ip_record.get('continent_code', ''),
            'country_iso_code': geo_ip_record.get('country_iso_code', ''),
            'city_in_en': geo_ip_record.get('city_in_en', ''),
            'as_number': geo_ip_record.get('as_number', ''),
            'as_organization': geo_ip_record.get('as_organization', ''),
            'isp_ame': geo_ip_record.get('isp_name', ''),
            'network': geo_ip_record.get('network', ''),
        },
        'country_rating': rating.get('country_rating', LOCATION_UNKNOWN).replace('location_', ''),
        'continent_rating': rating.get('continent_rating', LOCATION_UNKNOWN).replace('location_', ''),
    }

    return rating.get('overall_rating', LOCATION_UNKNOWN), evidence


def rate(geo_ip_record: dict, policy: dict):
    continent_rating = _extracted_from_rate_3(geo_ip_record, 'continent_code', 'continent', policy)
    country_rating = _extracted_from_rate_3(geo_ip_record, 'country_iso_code', 'country', policy)

    # country rating is more specific and thus more important than continent rating
    if SEVERITY_ORDER.index(country_rating) > SEVERITY_ORDER.index(continent_rating):
        overall_rating = country_rating
    else:
        overall_rating = continent_rating

    return {
        'continent_rating': continent_rating,
        'country_rating': country_rating,
        'overall_rating': overall_rating
    }


# TODO Rename this here and in `rate`
def _extracted_from_rate_3(geo_ip_record, arg1, c_or_c, policy):
    found_code = geo_ip_record.get(arg1, '')
    result = ""
    if found_code in policy[f'{c_or_c}_high']:
        result = LOCATION_HIGH
    if found_code in policy[f'{c_or_c}_low']:
        result = LOCATION_LOW
    if found_code in policy[f'{c_or_c}_medium']:
        result = LOCATION_MEDIUM
    if found_code not in policy[f'{c_or_c}_ok']:
        result = LOCATION_OK
    if not result:
        result = LOCATION_UNKNOWN

    return result


def get_policy(geography_type: str = 'web_server'):
    if geography_type not in SUPPORTED_GEOGRAPHY_TYPES:
        raise ValueError(f"content_type must be one of {SUPPORTED_GEOGRAPHY_TYPES}, got {geography_type}")

    keys = {}
    if geography_type == "mail_server":
        keys = {
            'continent_ok': "GEOGRAPHY_EMAIL_SERVER_IN_CONTINENT_OK",
            'continent_low': "GEOGRAPHY_EMAIL_SERVER_IN_CONTINENT_LOW",
            'continent_medium': "GEOGRAPHY_EMAIL_SERVER_IN_CONTINENT_MEDIUM",
            'continent_high': "GEOGRAPHY_EMAIL_SERVER_IN_CONTINENT_HIGH",
            'country_ok': "GEOGRAPHY_EMAIL_SERVER_IN_COUNTRIES_OK",
            'country_low': "GEOGRAPHY_EMAIL_SERVER_IN_COUNTRIES_LOW",
            'country_medium': "GEOGRAPHY_EMAIL_SERVER_IN_COUNTRIES_MEDIUM",
            'country_high': "GEOGRAPHY_EMAIL_SERVER_IN_COUNTRIES_HIGH",
        }

    elif geography_type == "web_server":
        keys = {
            'continent_ok': "GEOGRAPHY_WEB_SERVER_IN_CONTINENT_OK",
            'continent_low': "GEOGRAPHY_WEB_SERVER_IN_CONTINENT_LOW",
            'continent_medium': "GEOGRAPHY_WEB_SERVER_IN_CONTINENT_MEDIUM",
            'continent_high': "GEOGRAPHY_WEB_SERVER_IN_CONTINENT_HIGH",
            'country_ok': "GEOGRAPHY_WEB_SERVER_IN_COUNTRIES_OK",
            'country_low': "GEOGRAPHY_WEB_SERVER_IN_COUNTRIES_LOW",
            'country_medium': "GEOGRAPHY_WEB_SERVER_IN_COUNTRIES_MEDIUM",
            'country_high': "GEOGRAPHY_WEB_SERVER_IN_COUNTRIES_HIGH",
        }
    elif geography_type == "website_content":
        keys = {
            'continent_ok': "GEOGRAPHY_WEBSITE_THIRD_PARTY_CONTENT_FROM_CONTINENT_OK",
            'continent_low': "GEOGRAPHY_WEBSITE_THIRD_PARTY_CONTENT_FROM_CONTINENT_LOW",
            'continent_medium': "GEOGRAPHY_WEBSITE_THIRD_PARTY_CONTENT_FROM_CONTINENT_MEDIUM",
            'continent_high': "GEOGRAPHY_WEBSITE_THIRD_PARTY_CONTENT_FROM_CONTINENT_HIGH",
            'country_ok': "GEOGRAPHY_WEBSITE_THIRD_PARTY_CONTENT_FROM_COUNTRIES_OK",
            'country_low': "GEOGRAPHY_WEBSITE_THIRD_PARTY_CONTENT_FROM_COUNTRIES_LOW",
            'country_medium': "GEOGRAPHY_WEBSITE_THIRD_PARTY_CONTENT_FROM_COUNTRIES_MEDIUM",
            'country_high': "GEOGRAPHY_WEBSITE_THIRD_PARTY_CONTENT_FROM_COUNTRIES_HIGH",
        }

    # to prevent highlighting a not defined issue:
    if not keys:
        raise ValueError(f"Keys empty! {SUPPORTED_GEOGRAPHY_TYPES}, got {geography_type}")

    return {
        'continent_ok': constance_cached_value(keys['continent_ok']),
        'continent_low': constance_cached_value(keys['continent_low']),
        'continent_medium': constance_cached_value(keys['continent_medium']),
        'continent_high': constance_cached_value(keys['continent_high']),
        'country_ok': constance_cached_value(keys['country_ok']),
        'country_low': constance_cached_value(keys['country_low']),
        'country_medium': constance_cached_value(keys['country_medium']),
        'country_high': constance_cached_value(keys['country_high']),
    }
