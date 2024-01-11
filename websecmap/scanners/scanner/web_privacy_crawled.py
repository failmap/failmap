"""
These are the same metrics and meanings as web_privacy but the source is much different. In this case it's coming
from crawled content / playwright browser scans. These are kicked off in the cookie_consent scans.
This code just retrieves the latest metrics per url and stores them as regular scans in the database so they can be
exported.

There are usually two crawl sessions per url, one with and one without consent. They could be stopped for many reasons.
The sessions are linked per endpoint, which is always an ipv4 https 443 endpoint.

In the end this code should be added to cookie_consent scanner after that scan has finished, as it's the same logic
only without the 'get the latest sessions per endpoint etc' code.

Todo: if time add some extra metric that compares the consent / no consent variants on meta level. Like pages
# visited etc...
"""
import json

from datetime import timezone, timedelta, datetime
from json import JSONDecodeError

from websecmap.celery import app

from websecmap.scanners.models import CookieScanSession
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.metric_constants import (
    WEB_PRIVACY_THIRD_PARTY_REQUESTS_CRAWLED_WITH_CONSENT,
    WEB_PRIVACY_TRACKING_CRAWLED_WITH_CONSENT,
    WEB_PRIVACY_COOKIES_CRAWLED_WITH_CONSENT,
    WEB_PRIVACY_THIRD_PARTY_REQUESTS_CRAWLED_NO_CONSENT,
    WEB_PRIVACY_TRACKING_CRAWLED_NO_CONSENT,
    WEB_PRIVACY_COOKIES_CRAWLED_NO_CONSENT,
    WEB_PRIVACY_TRACKING_TRACKERS_FOUND,
    WEB_PRIVACY_TRACKING_OK,
    WEB_PRIVACY_THIRD_PARTY_FOUND,
    WEB_PRIVACY_THIRD_PARTY_OK,
    WEB_PRIVACY_COOKIES_NEUTRAL,
    WEB_PRIVACY_TRACKING_ERROR,
    WEB_PRIVACY_THIRD_PARTY_ERROR,
    WEB_PRIVACY_COOKIES_ERROR,
    WEB_PRIVACY_THIRD_PARTY_DOMAINS_CRAWLED_WITH_CONSENT,
    WEB_PRIVACY_THIRD_PARTY_DOMAINS_CRAWLED_NO_CONSENT,
    WEB_PRIVACY_THIRD_PARTY_DOMAINS_NEUTRAL,
    WEB_PRIVACY_THIRD_PARTY_DOMAINS_ERROR,
)
from websecmap.scanners.scanner.web_privacy import product_meaning_from_cookies
from websecmap.scanners.scanner.web_privacy_resources.trackers import get_known_trackers_from_urls


def import_metrics_from_cookie_scan_sessions():
    # metrics are added after a cookie consent scan has finished, but we needed the existing data
    # to be imported as metrics as well. This solves that issue.
    scans = get_latest_scan_sessions_per_endpoint_with_and_without_consent()

    for endpoint, data in scans.items():
        if data["with_consent"]:
            store_session_as_regular_metrics(endpoint["with_consent"]).apply_async()
        else:
            store_session_as_regular_metrics(endpoint["without_consent"]).apply_async()


def get_latest_scan_sessions_per_endpoint_with_and_without_consent():
    # this code prevents an older scan from being processed as the latest scan.

    # because you don't know what the latest scans are, and it's a bit cryptic to do that in sql, use the kiss
    # approach. Just iterate over all scans and from there determine the latest ones. Use some assumptions
    # From there kick off the actual saving routines. Which keeps this task reasonably fast.
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)  #
    # don't get all related fields to keep things fast.
    sessions = (
        CookieScanSession.objects.all()
        .filter(at_when__gte=thirty_days_ago)
        .order_by("-at_when")
        .only("id", "endpoint", "stats", "at_when")
    )

    # endpoint id, points to a non-consent and with-consent scan session, which covers both scenarios and has
    # the id's.
    sessions_to_process = {}

    for session in sessions:
        # don't want to deal with sessions that are not complete at all...
        if "consent" not in session.stats:
            continue

        if session.endpoint.id not in sessions_to_process:
            sessions_to_process[session.endpoint.id] = {
                "with_consent": None,
                "without_consent": None,
            }

        # add the latest session if it is still missing:
        if session.stats["consent"] and sessions_to_process[session.endpoint.id]["with_consent"] is None:
            sessions_to_process[session.endpoint.id]["with_consent"] = session.id

        if not session.stats["consent"] and sessions_to_process[session.endpoint.id]["without_consent"] is None:
            sessions_to_process[session.endpoint.id]["without_consent"] = session.id

    return sessions_to_process


@app.task(queue="storage", ignore_result=True)
def store_session_as_regular_metrics(session_id: int):
    # get consent from session to see what to store it as...
    # see how to utilize the functions that are already there for web_privacy in order to save upon work.
    # location cookies and third party domains are not yet used...
    session = CookieScanSession.objects.filter(id=session_id).first()
    if not session:
        return

    store_third_party_requests_as_regular_metrics(session)
    store_cookies_as_regular_metrics(session)


def store_third_party_requests_as_regular_metrics(session: CookieScanSession):
    if "consent" not in session.stats:
        return

    if session.stats["consent"]:
        _third_party_request_metric = WEB_PRIVACY_THIRD_PARTY_REQUESTS_CRAWLED_WITH_CONSENT
        _tracking_metric = WEB_PRIVACY_TRACKING_CRAWLED_WITH_CONSENT
        _domain_metric = WEB_PRIVACY_THIRD_PARTY_DOMAINS_CRAWLED_WITH_CONSENT
    else:
        _third_party_request_metric = WEB_PRIVACY_THIRD_PARTY_REQUESTS_CRAWLED_NO_CONSENT
        _tracking_metric = WEB_PRIVACY_TRACKING_CRAWLED_NO_CONSENT
        _domain_metric = WEB_PRIVACY_THIRD_PARTY_DOMAINS_CRAWLED_NO_CONSENT

    if session.stop_reason == "unhandled_exception":
        store_endpoint_scan_result(
            _tracking_metric, session.endpoint.id, WEB_PRIVACY_TRACKING_ERROR, WEB_PRIVACY_TRACKING_ERROR, evidence="{}"
        )

        store_endpoint_scan_result(
            _third_party_request_metric,
            session.endpoint.id,
            WEB_PRIVACY_THIRD_PARTY_ERROR,
            WEB_PRIVACY_THIRD_PARTY_ERROR,
            evidence="{}",
        )

        store_endpoint_scan_result(
            _domain_metric,
            session.endpoint.id,
            WEB_PRIVACY_THIRD_PARTY_DOMAINS_ERROR,
            WEB_PRIVACY_THIRD_PARTY_DOMAINS_ERROR,
            evidence="{}",
        )
        return

    third_party_requests = [
        {
            "method": third_party_request.method,
            "resource_type": third_party_request.resource_type,
            # some confusion solved here: the URL in externalresource means the url where the external resource was
            # found. The url in the third party request is the one that is requested to the external resource,
            # this is not completely stored so it's now just domainname, which prevents some issues with
            # deduplication over time. But it's not AS exact and might need to be upgraded.
            "url": third_party_request.domainname,
            "post_data": "",
            # instead of storing each call per domain, there is just a counter now, which gives some indication
            # of how many requests of the same type where made.
            "count": third_party_request.count,
        }
        for third_party_request in session.external_resources.all()
    ]

    # sort the third party requests by url, so things stay the same even if the stuff is saved in a different order.
    third_party_requests = list(sorted(third_party_requests, key=lambda x: x["url"]))

    # below code looks a lot like the one on web_privacy, perhaps this can be merged. But that would make it harder
    # to understan perhaps
    third_party_domains = list(sorted(list({x["url"] for x in third_party_requests})))
    known_trackers = get_known_trackers_from_urls(third_party_domains)

    web_privacy_tracking_rating = WEB_PRIVACY_TRACKING_TRACKERS_FOUND if known_trackers else WEB_PRIVACY_TRACKING_OK
    store_endpoint_scan_result(
        scan_type=_tracking_metric,
        endpoint_id=session.endpoint.id,
        rating=web_privacy_tracking_rating,
        message=web_privacy_tracking_rating,
        evidence=known_trackers,
    )

    # no post data, so no truncation needed. It's already deduped.
    web_third_party_rating = WEB_PRIVACY_THIRD_PARTY_FOUND if third_party_requests else WEB_PRIVACY_THIRD_PARTY_OK
    store_endpoint_scan_result(
        scan_type=_third_party_request_metric,
        endpoint_id=session.endpoint.id,
        rating=web_third_party_rating,
        message=web_third_party_rating,
        evidence=json.dumps(third_party_requests),
    )

    # also add the domain thing, like usual...
    store_endpoint_scan_result(
        scan_type=_domain_metric,
        endpoint_id=session.endpoint.id,
        rating=WEB_PRIVACY_THIRD_PARTY_DOMAINS_NEUTRAL,
        message=WEB_PRIVACY_THIRD_PARTY_DOMAINS_NEUTRAL,
        evidence=json.dumps(third_party_domains),
    )


def try_load_json(data: str):
    try:
        return json.loads(data)
    except JSONDecodeError:
        return {}


def store_cookies_as_regular_metrics(session: CookieScanSession):
    if "consent" not in session.stats:
        return

    if session.stats["consent"]:
        _cookie_metric = WEB_PRIVACY_COOKIES_CRAWLED_WITH_CONSENT
    else:
        _cookie_metric = WEB_PRIVACY_COOKIES_CRAWLED_NO_CONSENT

    if session.stop_reason == "unhandled_exception":
        store_endpoint_scan_result(
            _cookie_metric, session.endpoint.id, WEB_PRIVACY_COOKIES_ERROR, WEB_PRIVACY_COOKIES_ERROR, evidence="{}"
        )

    # reconstruct timeless cookies from cookies in the database
    # the cookie field in the cookie object is not json, but a single quoted string. which makes auto parsing imposible
    # so we do a best guess by just assuming there is no double qoute in the value.
    timeless_cookies = []
    for cookie in session.cookies.all():
        cookie_value = cookie.cookie.replace("'", '"')
        if cookie := try_load_json(cookie_value):
            timeless_cookies.append(cookie)
    cookies = sorted(timeless_cookies, key=lambda x: x["name"])

    products = product_meaning_from_cookies(cookies)
    cookies_product_meaning = {
        "products": products["products"],
    }

    store_endpoint_scan_result(
        scan_type=_cookie_metric,
        endpoint_id=session.endpoint.id,
        rating=products["worst_purpose_rating"],
        message=WEB_PRIVACY_COOKIES_NEUTRAL,
        meaning=cookies_product_meaning,
        evidence=json.dumps(cookies),
    )
