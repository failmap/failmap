"""
OpenWPM is a firefox browser that logs all responses to a database, from there it is possible to extract
what visits have been made, if they are secure and to what parties these requests are made.
https://openwpm.readthedocs.io/en/latest/Schema-Documentation.html

Thanks to:
- https://codeberg.org/dataskydd.net/
- https://github.com/PrivacyScore/privacyscanner/tree/whotracksme/privacyscanner/scanmodules
"""
from typing import Any, Dict, List
import requests

from celery import group
from websecmap.app import log
from websecmap.app.constance import constance_cached_value
from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners import init_dict, plannedscan
from websecmap.scanners.models import Cookie, CookiePlacement, Endpoint, ExternalResource
from websecmap.scanners.plannedscan import retrieve_endpoints_from_urls
from websecmap.scanners.scanner.filter import filter_endpoints_only, generic_plan_scan, merge_endpoints_filter


SCANNER_NAME = "cookie_consent"

# narrow down to the most restrictive set of domains, as the scanner is/can be pretty heavy on resource
# Site should be the same on v4 and v6 anyway... so don't bother with differences
STANDARD_ENDPOINT_FILTER = {
    "protocol": "https",
    "is_dead": False,
    "url__is_dead": False,
    "url__not_resolvable": False,
    "ip_version": 4,
    "port": 443,
    "url__computed_subdomain": "",
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
    organizations_filter: dict = None,
    urls_filter: dict = None,
    endpoints_filter: dict = None,
    standard_filter: bool = True,
    **kwargs,
) -> group:
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    if standard_filter:
        log.debug("standard_filter: %s", STANDARD_ENDPOINT_FILTER)
        kwargs = merge_endpoints_filter(STANDARD_ENDPOINT_FILTER, **kwargs)
    urls = filter_endpoints_only(organizations_filter, urls_filter, **kwargs)
    log.debug("Scanning cookies on %s", urls)
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
    log.debug("Scanning cookies on %s", url)
    # this is a single threaded webserver. More tasks means more waiting. So keep the amount of tasks low enough
    # so the timeout is never reached in case all tasks turn into timeouts
    playwright_server = constance_cached_value("WEB_PRIVACY_SERVER").rstrip("/")
    depth = 2
    maxpages = 200
    timeout = 300
    request = f"{playwright_server}/cookieconsent?site={url}&depth={depth}&maxpages={maxpages}&timeout={timeout}"
    log.debug(request)

    try:
        # give request some extra timout to ensure it can respond within its own timeout
        response = requests.get(request, timeout=timeout + 30)
    except requests.exceptions.ReadTimeout:
        log.exception("Request timed out")
        return None

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError:
        log.exception("Request to tool failed")
        return None

    try:
        response_json = response.json()
    except requests.exceptions.InvalidJSONError:
        log.exception("Failed to parse response JSON")
        return None

    log.debug("Cookie metrics returned %s", response_json)
    return response_json


@app.task(queue="storage", ignore_result=True)
def store(result_data: Dict[str, Any], endpoint_id: int) -> None:
    if not result_data:
        return

    if type(result_data) == list:
        cookies = result_data
        external_resources = []
    else:
        cookies = result_data.get("cookies", [])
        external_resources = result_data.get("external_resources", [])

    for cookie in cookies:
        endpoint = Endpoint.objects.get(pk=endpoint_id)
        c = Cookie.objects.create(
            endpoint=endpoint,
            session_id=cookie.get("session_id"),
            depth=cookie.get("depth"),
            url=cookie.get("url")[:200],
            cookie=cookie.get("cookie"),
        )
        placements = [CookiePlacement.objects.get_or_create(name=name)[0] for name in cookie.get("placement", [])]
        c.placement.set(placements)
        c.save()

    for resource in external_resources:
        endpoint = Endpoint.objects.get(pk=endpoint_id)
        r = ExternalResource.objects.create(
            endpoint=endpoint,
            session_id=resource.get("session_id"),
            depth=resource.get("depth"),
            url=resource.get("url")[:200],
            domainname=resource.get("domainname"),
            resource_type=resource.get("type"),
            method=resource.get("method"),
            count=resource.get("count"),
        )
        attributes = [CookiePlacement.objects.get_or_create(name=name)[0] for name in resource.get("attributes", [])]
        r.attributes.set(attributes)
        r.save()
