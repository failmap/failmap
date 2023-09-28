"""
OpenWPM is a firefox browser that logs all responses to a database, from there it is possible to extract
what visits have been made, if they are secure and to what parties these requests are made.
https://openwpm.readthedocs.io/en/latest/Schema-Documentation.html

Thanks to:
- https://codeberg.org/dataskydd.net/
- https://github.com/PrivacyScore/privacyscanner/tree/whotracksme/privacyscanner/scanmodules
"""
from json import JSONDecodeError
from typing import Any, Dict, List
import re
import requests

from celery import group
from collections import defaultdict
from websecmap.app import log
from websecmap.app.constance import constance_cached_value
from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners import init_dict, plannedscan
from websecmap.scanners.comperators import third_party_request_is_present
from websecmap.scanners.models import Endpoint, EndpointGenericScan, ProductCookieIndicator, CookieIndicatorFields
from websecmap.scanners.plannedscan import retrieve_endpoints_from_urls
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.filter import filter_endpoints_only, generic_plan_scan, merge_endpoints_filter
from websecmap.scanners.scanner.metric_constants import (
    WEB_PRIVACY_TRACKING,
    WEB_PRIVACY_TRACKING_ERROR,
    WEB_PRIVACY_THIRD_PARTY_REQUESTS,
    WEB_PRIVACY_THIRD_PARTY_ERROR,
    WEB_PRIVACY_COOKIES,
    WEB_PRIVACY_COOKIES_ERROR,
    WEB_PRIVACY_THIRD_PARTY_DOMAINS,
    WEB_PRIVACY_THIRD_PARTY_FOUND,
    WEB_PRIVACY_THIRD_PARTY_OK,
    WEB_PRIVACY_TRACKING_OK,
    WEB_PRIVACY_TRACKING_TRACKERS_FOUND,
    WEB_PRIVACY_COOKIES_NEUTRAL,
    WEB_PRIVACY_THIRD_PARTY_DOMAINS_NEUTRAL,
    WEB_PRIVACY_THIRD_PARTY_DOMAINS_ERROR,
)

from websecmap.scanners.scanner.web_privacy_resources.trackers import get_known_trackers_from_urls
import json

from websecmap.scanners.scanner_for_everything.location import (
    meaning_of_location_at_web_privacy_cookies,
    SCAN_TYPE_LOCATION_COOKIES,
)
from websecmap.utils import normalize_cookies

SCANNER_NAME = "web_privacy"

# narrow down to the most restrictive set of domains, as the scanner is/can be pretty heavy on resource
# Site should be the same on v4 and v6 anyway... so don't bother with differences
STANDARD_ENDPOINT_FILTER = {
    "protocol": "https",
    "is_dead": False,
    "url__is_dead": False,
    "url__not_resolvable": False,
    "ip_version": 4,
    "port": 443,
}


@app.task(queue="kickoff", ignore_result=True)
def plan_scan(**kwargs) -> None:
    kwargs = merge_endpoints_filter(STANDARD_ENDPOINT_FILTER, **kwargs)
    generic_plan_scan(SCANNER_NAME, "scan", filter_endpoints_only, **kwargs)


@app.task(queue="kickoff")
def compose_planned_scan_task(**kwargs) -> group:
    urls = plannedscan.pickup(activity="scan", scanner=SCANNER_NAME, amount=kwargs.get("amount", 25))
    return compose_scan_task(urls)


def compose_manual_scan_task(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> group:
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    kwargs = merge_endpoints_filter(STANDARD_ENDPOINT_FILTER, **kwargs)
    urls = filter_endpoints_only(organizations_filter, urls_filter, **kwargs)
    log.debug("Scanning privacy on %s", urls)
    return compose_scan_task(urls)


def compose_scan_task(urls: List[Url]) -> group:
    https_endpoints, https_urls_without_endpoints = retrieve_endpoints_from_urls(
        urls, protocols=["https"], ports=[443], ip_versions=[4]
    )

    tasks = [plannedscan.finish.si("scan", SCANNER_NAME, url_id) for url_id in https_urls_without_endpoints]
    tasks.extend(
        group(
            scan.si(endpoint.uri_url())
            | store.s(endpoint.id)
            | plannedscan.finish.si("scan", SCANNER_NAME, endpoint.url.id)
        )
        for endpoint in https_endpoints
    )
    return group(tasks)


@app.task(queue="playwright-privacy", ignore_result=True)
def scan(url: str) -> Dict[str, Any]:
    # just except the loudest way possible in case of exceptions.
    log.debug("Scanning privacy on %s", url)
    # this is a single threaded webserver. More tasks means more waiting. So keep the amount of tasks low enough
    # so the timeout is never reached in case all tasks turn into timeouts
    response = requests.get(f"{constance_cached_value('WEB_PRIVACY_SERVER')}?site={url}", timeout=300).json()
    log.debug("Privacy metrics returned %s", response)
    return response


@app.task(queue="storage", ignore_result=True)
def store(result_data: Dict[str, Any], endpoint_id: int) -> None:
    """
    {
      "third-party-requests": [
        "https://ab.tweakers.nl/pool/lib/3751_0.gif",
        "https://aa.tweakers.nl/json",
        ...
      ],
      "third-party-domains": [
        "ab.tweakers.nl",
        "aa.tweakers.nl"
      ],
      "third-party-top-level-domains": [
        "tweakers.nl"
      ],
      "cookies": [
        {
          "name": "__Secure-TnetID",
          "value": ".0ZJcr8PVkq_xDqzVBaqpqFrJG4Jhikgj",
          "domain": ".tweakers.net",
          "path": "/",
          "expires": 1683477449.479243,
          "httpOnly": false,
          "secure": true,
          "sameSite": "Lax"
        },
        ...
      ],
      "timeless-cookies": [
        {
          "name": "__Secure-TnetID",
          "domain": ".tweakers.net",
          "path": "/",
          "httpOnly": false,
          "secure": true,
          "sameSite": "Lax"
        },
        ...
      ],
      "headers": {
        "cache-control": "max-age=0, private",
        "content-encoding": "gzip",
        "content-security-policy": "default-src https: data: blob: 'unsafe-inline' 'unsafe-eval'; ...
        "content-type": "text/html; charset=UTF-8",
        "date": "Wed, 03 May 2023 16:37:29 GMT",
        "expires": "-1",
        "server": "Apache",
        "strict-transport-security": "max-age=31536000; includeSubDomains; preload",
        "vary": "Accept-Encoding",
        "x-clacks-overhead": "GNU Terry Pratchett, Yoeri Lauwers, Arie Jan Stapel",
        "x-content-type-options": "nosniff",
        "x-tweakers-server": "twk-eun-web1",
        "x-xss-protection": "1; mode=block"
      },
      "security_details": {
        "issuer": "R3",
        "protocol": "TLS 1.3",
        "subjectName": "*.tweakers.net",
        "validFrom": 1682935528,
        "validTo": 1690711527
      },
      "status": 200
    }

    """

    endpoint = Endpoint.objects.all().filter(id=endpoint_id).first()
    if not endpoint:
        return

    if error := result_data.get("error"):
        store_endpoint_scan_result(
            WEB_PRIVACY_TRACKING, endpoint_id, WEB_PRIVACY_TRACKING_ERROR, WEB_PRIVACY_TRACKING_ERROR, evidence=error
        )
        store_endpoint_scan_result(
            WEB_PRIVACY_THIRD_PARTY_REQUESTS,
            endpoint_id,
            WEB_PRIVACY_THIRD_PARTY_ERROR,
            WEB_PRIVACY_THIRD_PARTY_ERROR,
            evidence=error,
        )
        store_endpoint_scan_result(
            WEB_PRIVACY_COOKIES, endpoint_id, WEB_PRIVACY_COOKIES_ERROR, WEB_PRIVACY_COOKIES_ERROR, evidence=error
        )

        store_endpoint_scan_result(
            WEB_PRIVACY_THIRD_PARTY_DOMAINS,
            endpoint_id,
            WEB_PRIVACY_THIRD_PARTY_DOMAINS_ERROR,
            WEB_PRIVACY_THIRD_PARTY_DOMAINS_ERROR,
            evidence=error,
        )

        return

    third_party_requests = result_data.get("third-party-requests-structured", [])
    # it's easy to have more than 9000 characters with third party stuff. there make this shorter
    # This removes urls with the same parameters but different content. As that's just more of the same.
    third_party_requests = remove_duplicate_third_party_requests(third_party_requests)
    # limit the total amount of requests to 500, which is already more than insanely ridiculous.
    # That would mean several fonts, tons of images, external css and whatnot. This prevents that the
    # evidence grows to gigabytes.
    third_party_requests = third_party_requests[:500]
    # don't store extremely long post data, which has little value. 200 chars is already insane for a site visit.
    third_party_requests = truncate_long_post_data(third_party_requests, 200)
    third_party_domains = result_data.get("third-party-domains", [])
    # timeless-cookies are cookies with unique components (like: value, timestamp) stripped
    cookies = normalize_cookies(result_data.get("timeless-cookies", []))

    known_trackers = get_known_trackers_from_urls(third_party_domains)

    # happens sometimes, where it should not
    web_privacy_tracking_rating = WEB_PRIVACY_TRACKING_TRACKERS_FOUND if known_trackers else WEB_PRIVACY_TRACKING_OK
    store_endpoint_scan_result(
        scan_type=WEB_PRIVACY_TRACKING,
        endpoint_id=endpoint_id,
        rating=web_privacy_tracking_rating,
        message=web_privacy_tracking_rating,
        evidence=known_trackers,
    )

    # happens a lot, due to easiest path of development / culture
    # todo: to avoid duplicate findings ignore content of parameters, only check for parameters and addresses
    web_third_party_rating = WEB_PRIVACY_THIRD_PARTY_FOUND if third_party_requests else WEB_PRIVACY_THIRD_PARTY_OK
    store_endpoint_scan_result(
        scan_type=WEB_PRIVACY_THIRD_PARTY_REQUESTS,
        endpoint_id=endpoint_id,
        rating=web_third_party_rating,
        message=web_third_party_rating,
        evidence=json.dumps(third_party_requests),
    )

    products = product_meaning_from_cookies(cookies)
    cookies_meaning = {
        "products": products,
    }

    # also store cookies for later inspection
    store_endpoint_scan_result(
        scan_type=WEB_PRIVACY_COOKIES,
        endpoint_id=endpoint_id,
        rating=WEB_PRIVACY_COOKIES_NEUTRAL,
        message=WEB_PRIVACY_COOKIES_NEUTRAL,
        meaning=cookies_meaning,
        evidence=json.dumps(cookies),
    )

    locations_worst_rating, locations_rating_series = meaning_of_location_at_web_privacy_cookies(cookies)
    cookies_location_meaning = {
        "locations_worst_rating": locations_worst_rating,
        "locations": locations_rating_series,
    }

    store_endpoint_scan_result(
        scan_type=SCAN_TYPE_LOCATION_COOKIES,
        endpoint_id=endpoint_id,
        rating=locations_worst_rating,
        message=locations_worst_rating,
        meaning=cookies_location_meaning,
        evidence=json.dumps(cookies),
    )

    store_endpoint_scan_result(
        scan_type=WEB_PRIVACY_THIRD_PARTY_DOMAINS,
        endpoint_id=endpoint_id,
        rating=WEB_PRIVACY_THIRD_PARTY_DOMAINS_NEUTRAL,
        message=WEB_PRIVACY_THIRD_PARTY_DOMAINS_NEUTRAL,
        evidence=json.dumps(third_party_domains),
    )


def product_meaning_from_cookies(cookies: list = []) -> dict[str:Any]:
    """Generate list of products determined from cookies."""
    cookie_indicators = list()

    for indicator in ProductCookieIndicator.objects.all():
        matchers = dict()
        if indicator.match_name:
            matchers["name"] = re.compile(f"^{indicator.match_name}$")
        if indicator.match_domain:
            matchers["domain"] = re.compile(f"^{indicator.match_domain}$")
        if indicator.match_path:
            matchers["path"] = re.compile(f"^{indicator.match_path}$")
        cookie_indicators.append((matchers, indicator.product))

    products = defaultdict(lambda: dict([["cookies", list()]]))
    for cookie in cookies:
        for matchers, product in cookie_indicators:
            if all(matcher.match(cookie[field]) for field, matcher in matchers.items()):
                products[product.id]["product_id"] = product.id
                products[product.id]["product_name"] = product.name
                products[product.id]["product_version"] = "unknown"
                products[product.id]["cookies"].append(strip_irrelevant_cookie_fields(cookie))
                break
        else:
            log.debug(f"No product match for cookie: {cookie}")

    return products.values()


def strip_irrelevant_cookie_fields(cookie: dict, keep_fields={x[1] for x in CookieIndicatorFields.choices}) -> dict:
    """Strip fields from cookies that where not used to determine product."""
    return {k: cookie[k] for k in cookie if k in keep_fields}


def privacy_counters(add_urls: bool = False) -> None:
    scans = EndpointGenericScan.objects.all().filter(
        type="web_privacy_tracking",
        is_the_latest_scan=True,
        endpoint__is_dead=False,
        endpoint__url__is_dead=False,
        endpoint__url__not_resolvable=False,
    )
    # todo: specify layers
    keys = ["Company", "Platform", "Tracking Url"]
    for key in keys:
        companies = {}
        for scan in scans:
            try:
                evidence = json.loads(scan.evidence.replace("'", '"'))
                for tracker in evidence:
                    if tracker[key] not in companies:
                        companies[tracker[key]] = {"amount": 0, "urls": []}
                    companies[tracker[key]]["amount"] += 1
                    if add_urls:
                        companies[tracker[key]]["urls"].append(scan.endpoint.url.url)
            except JSONDecodeError:
                pass
        print(key)
        print(json.dumps(companies, indent=4))


def truncate_long_post_data(third_party_requests: List[Dict[str, str]], max_chars: int = 60) -> List[Dict[str, str]]:
    """
    60 characters is long enough to see what about is being sent, but to too long.
      {
        "url": "https://cuatro.sim-cdn.nl/assets/1.93.0/iconFonts/fontawesome6/css/fontawesome.6.4.0.css",
        "resource_type": "stylesheet",
        "method": "GET",
        "post_data": null
      },
    """

    truncation_message_length = 35
    for request in third_party_requests:
        if request["post_data"] and len(request["post_data"]) > max_chars + truncation_message_length:
            truncated = len(request["post_data"][max_chars:])
            request["post_data"] = request["post_data"][:max_chars] + "... truncated " + str(truncated) + " characters"

    return third_party_requests


def remove_duplicate_third_party_requests(third_party_requests: List[Dict[str, str]]) -> List[Dict[str, str]]:
    # Removes urls that have the same set of parameters but with different values. Urls themselves on face value
    # are already unique, but ignoring the parameters can make them not be unique.
    # This only works when urls are still in-tact. It might be possible that urls are not compliant with the uri schema
    #

    new_list = []
    for request in third_party_requests:
        if not third_party_request_is_present(request, new_list):
            new_list.append(request)
    return new_list
