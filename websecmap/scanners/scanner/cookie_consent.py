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
from websecmap.scanners.models import (
    Cookie,
    CookiePlacement,
    CookieBanner,
    Endpoint,
    ExternalResource,
    CookieScanSession,
    PaperTrail,
    CookieBannerAttribute,
)
from websecmap.scanners.plannedscan import retrieve_endpoints_from_urls
from websecmap.scanners.scanner.filter import filter_endpoints_only, generic_plan_scan, merge_endpoints_filter
import base64
from django.core.files.base import ContentFile

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
            [
                scan.si(endpoint.uri_url(), True)
                | group(
                    [
                        store.s(endpoint.id) | plannedscan.finish.si("scan", SCANNER_NAME, endpoint.url.id),
                        store_paper_trail.s(endpoint.id),
                    ]
                ),
                scan.si(endpoint.uri_url(), False)
                | group(
                    [
                        store.s(endpoint.id) | plannedscan.finish.si("scan", SCANNER_NAME, endpoint.url.id),
                        store_paper_trail.s(endpoint.id),
                    ]
                ),
            ]
        )
        for endpoint in https_endpoints
    )
    return group(tasks)


@app.task(queue="cookie-consent", ignore_result=True)
def scan(url: str, consent: bool) -> Dict[str, Any]:
    # just except the loudest way possible in case of exceptions.
    log.debug("Scanning cookies on %s", url)
    # this is a single threaded webserver. More tasks means more waiting. So keep the amount of tasks low enough
    # so the timeout is never reached in case all tasks turn into timeouts
    playwright_server = constance_cached_value("WEB_COOKIE_CONSENT").rstrip("/")
    depth = constance_cached_value("COOKIE_CRAWL_DEPTH")
    maxpages = constance_cached_value("COOKIE_CRAWL_MAXPAGES")
    crawl_time = constance_cached_value("COOKIE_CRAWL_TIME")
    timeout = 300 + crawl_time  # add default timeout on top of crawl timeout
    params = {
        "site": url,
        "depth": depth,
        "maxpages": maxpages,
        "timeout": crawl_time,
        "consent": "1" if consent else "0",
    }
    request = f"{playwright_server}/cookieconsent"

    try:
        log.debug("url:%s params:%s timeout:%s", request, params, timeout)
        response = requests.get(request, params=params, timeout=timeout)
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

    session_id = result_data.get("meta").get("session_id")
    endpoint = Endpoint.objects.get(pk=endpoint_id)

    cookies = result_data.get("cookies", [])
    external_resources = result_data.get("external_resources", [])
    banners = result_data.get("banners", [])
    stats = result_data.get("meta", {}).get("stats", {})
    stop_reason = result_data.get("meta", {}).get("stop_reason", None)

    session, created = CookieScanSession.objects.get_or_create(
        id=session_id, endpoint=endpoint, stats=stats, stop_reason=stop_reason
    )
    session.save()

    for cookie in cookies:
        c = Cookie.objects.create(
            endpoint=endpoint,
            session_id=session_id,
            depth=cookie.get("depth"),
            url=cookie.get("url")[:200],
            cookie=cookie.get("cookie"),
        )
        placements = [CookiePlacement.objects.get_or_create(name=name)[0] for name in cookie.get("placement")]
        c.placement.set(placements)
        c.save()
        session.cookies.add(c)

    for resource in external_resources:
        r = ExternalResource.objects.create(
            endpoint=endpoint,
            session_id=session_id,
            depth=resource.get("depth"),
            url=resource.get("url")[:200],
            domainname=resource.get("domainname"),
            resource_type=resource.get("type"),
            method=resource.get("method"),
            count=resource.get("count"),
        )
        attributes = [CookiePlacement.objects.get_or_create(name=name)[0] for name in resource.get("attributes")]
        r.attributes.set(attributes)
        r.save()
        session.external_resources.add(r)

    for banner in banners:
        cb = CookieBanner.objects.create(
            endpoint=endpoint,
            session_id=session_id,
            indicator=banner.get("indicator"),
        )

        attribute = [CookieBannerAttribute.objects.get_or_create(name=name)[0] for name in banner.get("attributes", [])]
        cb.attributes.set(attribute)
        cb.save()

        session.banners.add(cb)

    session.save()


@app.task(queue="storage", ignore_result=True)
def store_paper_trail(result_data: Dict[str, Any], endpoint_id: int) -> None:
    """Stores all paper trails from a scan in persistent long term storage (disk, S3 glacier, etc)."""

    if not result_data:
        return

    session_id = int(result_data["meta"]["session_id"])
    paper_trails = result_data["meta"].get("paper_trails", {})

    if not paper_trails:
        log.debug("no paper trails for scansession: %s", session_id)
        return

    endpoint = Endpoint.objects.get(pk=endpoint_id)

    session, created = CookieScanSession.objects.get_or_create(id=session_id, endpoint=endpoint)

    for filename, base64_content in paper_trails.items():
        try:
            name = f"{SCANNER_NAME}/{session_id}/{filename}"
            content = base64.b64decode(base64_content)
            p = PaperTrail(filename=filename, file_object=ContentFile(content, name=name))
            p.save()
            session.paper_trails.add(p)
        except Exception:
            # log exception, but continue to next file to be saved
            log.exception("Failed to save paper trail")

    session.save()
