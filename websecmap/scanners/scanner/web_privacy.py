"""
OpenWPM is a firefox browser that logs all responses to a database, from there it is possible to extract
what visits have been made, if they are secure and to what parties these requests are made.
https://openwpm.readthedocs.io/en/latest/Schema-Documentation.html

Thanks to:
- https://codeberg.org/dataskydd.net/
- https://github.com/PrivacyScore/privacyscanner/tree/whotracksme/privacyscanner/scanmodules
"""
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import requests
import tldextract
from celery import group

from websecmap.app import log
from websecmap.app.constance import constance_cached_value
from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners import init_dict, plannedscan
from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.plannedscan import retrieve_endpoints_from_urls
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.__init__ import allowed_to_scan
from websecmap.scanners.scanner.filter import filter_endpoints_only, generic_plan_scan, merge_endpoints_filter
from websecmap.scanners.scanner.web_privacy_resources.trackers import get_known_trackers_from_urls
import json

SCANNER_NAME = "web_privacy"

# narrow down to the most restrictive set of domains, as the scanner is/can be pretty heavy on resource
# Site should be the same on v4 and v6 anyway... so don't bother with differences
STANDARD_ENDPOINT_FILTER = {
    "protocol": "https",
    "is_dead": False,
    "url__computed_subdomain": "",
    "url__is_dead": False,
    "url__not_resolvable": False,
    "ip_version": 4,
    "port": 443,
}


# Metrics:
WEB_PRIVACY_THIRD_PARTY_REQUESTS = "web_privacy_third_party_requests"
WEB_PRIVACY_THIRD_PARTY_FOUND = "web_privacy_third_party_found"
WEB_PRIVACY_THIRD_PARTY_OK = "web_privacy_third_party_ok"

WEB_PRIVACY_TRACKING = "web_privacy_tracking"
WEB_PRIVACY_TRACKING_TRACKERS_FOUND = "web_privacy_tracking_trackers_found"
WEB_PRIVACY_TRACKING_OK = "web_privacy_tracking_ok"


@app.task(queue="kickoff", ignore_result=True)
def plan_scan(**kwargs) -> None:
    # todo: only domains, no subdomains at first.
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
    if not allowed_to_scan(SCANNER_NAME):
        return group()

    kwargs = merge_endpoints_filter(STANDARD_ENDPOINT_FILTER, **kwargs)
    urls = filter_endpoints_only(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    return compose_scan_task(urls)


def compose_scan_task(urls: List[Url]) -> group:
    # todo: on endpoint level, is easier for storage
    return group([scan.si([url.id for url in urls])])


@app.task(queue="storage", ignore_result=True)
def scan_and_store(url_ids: List[int]):
    # https://codeberg.org/dataskydd.net/municipality-privacy/src/branch/main/openwpm_municipalities.py
    """
    # storing and such is async. Storing happens from the shared database...
    | store.s(url.pk)
    | plannedscan.finish.si("scan", SCANNER_NAME, url.pk)
    """
    # get the endpoints that can be scanned:
    endpoints_to_scan_ids = scan(url_ids)
    for ep_id in endpoints_to_scan_ids:
        store(ep_id)


@app.task(queue="openwpm", ignore_result=True)
def scan(url_ids: List[int]) -> List[int]:
    # Just scan, and separate storing the results to the store method. This allows for individual tasks to be run

    # get the endpoints that can be scanned:
    endpoints_to_scan = []
    for url_id in url_ids:
        if eps := check_administration(url_id):
            endpoints_to_scan.append(eps[0])

    fqdn_urls = [f"{ep.protocol}://{ep.url.url}/" for ep in endpoints_to_scan]
    requests.post(constance_cached_value("WEB_PRIVACY_SERVER"), json={"sites": fqdn_urls}, timeout=30).json()

    # finish them, importing results is done async, otherwise we'll always be waiting till everything is done and
    # possibly be waiting forever if there are crashes, skipped endpoints/urls etc...
    for url_id in url_ids:
        plannedscan.finish("scan", SCANNER_NAME, url_id)

    return [ep.id for ep in endpoints_to_scan]


def check_administration(url_id: int) -> List[Endpoint]:
    # administration:
    url = Url.objects.filter(pk=url_id, is_dead=False, not_resolvable=False).first()
    if not url:
        log.debug("Privacy scan could not start, url not found in database or not alive/resolvable.")
        plannedscan.finish("scan", SCANNER_NAME, url_id)
        return []

    eps, urls_without_eps = retrieve_endpoints_from_urls(urls=[url], protocols=["https"], ports=[443], ip_versions=[4])
    if urls_without_eps:
        log.debug("Privacy scan could not start, no endpoints that match our criteria exist.")
        plannedscan.finish("scan", SCANNER_NAME, url_id)
        return []

    return eps


def latest_visit_id(url: str) -> Dict[str, int]:
    # todo: we should look at the http_redirects table as well
    log.debug("Looking at the latest visit for: %s", url)
    # latest_visit_id url expects a slash on the end, include a protocol...

    # Get the http_request that is at the origin of the current site_visit. From there you get the visit_id.
    # You can see if a visit is done when the id is removed from the incomplete_visits table.
    sql = """SELECT visit_id from http_requests where url = ?
    AND triggering_origin = 'undefined' AND loading_origin = 'undefined'
    AND loading_href = 'undefined' AND resource_type = 'main_frame'
    AND url = top_level_url
    ORDER BY id DESC LIMIT 1"""

    db = NinetiesDatabase()
    return db.first_value(sql, [url])


@app.task(queue="storage", ignore_result=True)
def store(endpoint_id: int) -> None:
    """
    https://openwpm.readthedocs.io/en/latest/Schema-Documentation.html

    Todo:
    - Count cookies and third party cookies
    - See if google uses 'anonymize requests'
    """

    endpoint = Endpoint.objects.all().filter(id=endpoint_id).first()
    if not endpoint:
        return

    # todo: is this compatible with forwards to other domains / cookie consent domains? Does that even happen?
    domain = f"{endpoint.url.computed_domain}.{endpoint.url.computed_suffix}"
    domain_inc_subdomain = domain
    if endpoint.url.computed_subdomain:
        domain_inc_subdomain = f"{endpoint.url.computed_subdomain}.{domain}"

    visit_id = latest_visit_id(f"{endpoint.protocol}://{domain_inc_subdomain}/")
    if not visit_id:
        log.debug("No visit id found for: %s", domain_inc_subdomain)
        # cannot add conclusions if we didn't measure...
        return

    visit_id = visit_id["visit_id"]

    third_party_requests, third_party_domains = get_third_party_requests(visit_id, domain, domain_inc_subdomain)
    known_trackers = get_known_trackers_from_urls(third_party_domains)

    # happens sometimes, where it should not
    web_privacy_tracking_rating = WEB_PRIVACY_TRACKING_TRACKERS_FOUND if known_trackers else WEB_PRIVACY_TRACKING_OK
    store_endpoint_scan_result(
        WEB_PRIVACY_TRACKING,
        endpoint_id,
        web_privacy_tracking_rating,
        message=web_privacy_tracking_rating,
        evidence=known_trackers,
    )

    # happens a lot, due to easiest path of development / culture
    web_third_party_rating = WEB_PRIVACY_THIRD_PARTY_FOUND if third_party_requests else WEB_PRIVACY_THIRD_PARTY_OK
    store_endpoint_scan_result(
        WEB_PRIVACY_THIRD_PARTY_REQUESTS,
        endpoint_id,
        web_third_party_rating,
        message=web_third_party_rating,
        evidence="\n".join(third_party_requests),
    )

    # Don't finish a scan here, as this might be an older result from an older scan on the same endpoint etc.
    # plannedscan.finish.si("scan", SCANNER_NAME, endpoint.url.id)


def get_top_level_domains_from_database():
    # todo: import_scan_result_database
    # Instead of waiting for a scan to finish, read what domains are in the database and add ratings from there.
    # This allows for easier separation of scanning and importing results.
    # As long as the process does not write to the sqlite db, it will be fine.
    # We only want the newest results...

    sql = """
    SELECT visit_id, top_level_url from http_requests WHERE
    triggering_origin = 'undefined' AND loading_origin = 'undefined'
    AND loading_href = 'undefined' AND resource_type = 'main_frame'
    AND url = top_level_url AND time_stamp > ? AND time_stamp < ?
    ORDER BY id"""

    db = NinetiesDatabase()
    # Only get stuff from the last 7 days.
    # Sqlite does not understand dates, but since it's iso you can sort of filter "per day". Therefore we add 1 day
    # so the stuff from "today" is retrieved. (everything less than tomorrow.
    return db.rows(
        sql, [datetime.now(timezone.utc) - timedelta(days=7), datetime.now(timezone.utc) + timedelta(days=1)]
    )


@app.task(queue="storage", ignore_result=True)
def import_scan_result_database_async():
    # It's possible the same domain is in this set a few time, so only get the one returned first (with the higher)
    # id, which has the newer results.
    domain_rows = get_top_level_domains_from_database()
    # see if there is a matching endpoint

    done_top_level_urls = []
    for row_data in domain_rows:
        top_level_url = row_data["top_level_url"]
        log.debug("Starting attempted privacy import from %s", top_level_url)

        # if there are more than 3 slashes its a folder, we don't do folders:
        if top_level_url.count("/") > 3:
            log.debug("- Url has too many slashes, so is not the root of the domain: %s", top_level_url)
            continue

        # don't import the same domain twice, remove https and all the rest to better handle duplicates
        if top_level_url in done_top_level_urls:
            log.debug("- Already imported: %s", top_level_url)
            continue
        done_top_level_urls.append(top_level_url)

        domain = extract_full_domain(top_level_url)
        url = Url.objects.all().filter(url=domain).first()
        if not url:
            log.debug("- No url found for: %s", domain)
            continue

        # filter to the set we want to tailor for.
        protocol = "https" if "https" in top_level_url else "http"
        endpoint = (
            Endpoint.objects.all().filter(url=url, protocol=protocol, ip_version=4, port=443, is_dead=False).first()
        )
        if not endpoint:
            log.debug("- No endpoint found for: %s://%s on port 443, ipv4", protocol, domain)
            continue

        # looks good, let's import all there is...
        store(endpoint.id)


def extract_full_domain(long_uri: str) -> str:
    result = tldextract.extract(long_uri)
    return result.fqdn


def get_third_party_requests(visit_id: int, domain: str, domain_inc_subdomain: str) -> Tuple[List[str], List[str]]:
    log.debug(
        "Getting third party requests from visit %s, domain: %s, inc sub: %s", visit_id, domain, domain_inc_subdomain
    )

    all_requests = get_all_requests(visit_id)
    third_party_requests = []
    third_party_domains = []
    third_party_urls = []

    # todo: this possible breaks with forwards
    for request in all_requests:
        # +20 = "https://www."
        if domain not in request["url"][: len(domain_inc_subdomain) + 14]:
            third_party_requests.append(request)
            third_party_domains.append(extract_full_domain(request["url"]))
            third_party_urls.append(request["url"])

    return list(set(third_party_urls)), list(set(third_party_domains))


def get_all_requests(visit_id: int) -> List[Dict[str, Any]]:
    db = NinetiesDatabase()
    return db.rows("SELECT * FROM http_responses where visit_id = ?", [visit_id])


class NinetiesDatabase:
    conn = None

    def __init__(self, db_location: str = None):
        # make it easier for testing
        if not db_location:
            db_location = constance_cached_value("WEB_PRIVACY_DATABASE_LOCATION")

        self.conn = sqlite3.connect(db_location, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)

        def dict_factory(cursor, row):
            fields = [column[0] for column in cursor.description]
            return dict(zip(fields, row))

        self.conn.row_factory = dict_factory

    def first_value(self, query: str, params: List[Any]):
        cur = self.conn.cursor()
        cur.execute(query, params)

        return cur.fetchone()

    def rows(self, query: str, params: List[Any]) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(query, params)
        return cur.fetchall()

    def __del__(self):
        if self.conn:
            self.conn.close()


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
            evidence = json.loads(scan.evidence.replace("'", '"'))
            for tracker in evidence:
                if tracker[key] not in companies:
                    companies[tracker[key]] = {"amount": 0, "urls": []}
                companies[tracker[key]]["amount"] += 1
                if add_urls:
                    companies[tracker[key]]["urls"].append(scan.endpoint.url.url)
        print(key)
        print(json.dumps(companies, indent=4))
