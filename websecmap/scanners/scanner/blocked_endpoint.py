"""
Checks if an endpoint has blocked us by attempting to visit the endpoint via different routes.
"""


import contextlib
import logging
from typing import Dict, Any

import requests
from celery import Task, group
from requests import RequestException

from websecmap.celery import app
from websecmap.scanners import init_dict, plannedscan
from websecmap.scanners.models import ScanProxy
from websecmap.scanners.plannedscan import retrieve_endpoints_from_urls
from websecmap.scanners.proxy import check_proxy
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.__init__ import allowed_to_scan, unique_and_random
from websecmap.scanners.scanner.filter import (
    filter_endpoints_only,
    generic_plan_scan,
    merge_endpoints_filter,
)

from websecmap.scanners.scanner.utils import CELERY_IP_VERSION_QUEUE_NAMES

log = logging.getLogger(__name__)

SCANNER_NAME = "blocked_endpoint"
# if they block us, it's usually an ipv4 firewall that does that automatically
STANDARD_ENDPOINT_FILTER = {"protocol__in": ["http", "https"], "ip_version": 4}

FINDING_BE_BLOCKED = "blocked_endpoint_blocked"
FINDING_BE_REACHABLE = "blocked_endpoint_reachable"
FINDING_BE_NOT_REACHABLE = "blocked_endpoint_not_reachable"

PROXY_NETWORK_TIMEOUT = 20
PROXY_SERVER_TIMEOUT = 20


@app.task(queue="kickoff", ignore_result=True)
def plan_scan(**kwargs):
    kwargs = merge_endpoints_filter(STANDARD_ENDPOINT_FILTER, **kwargs)
    generic_plan_scan(SCANNER_NAME, "scan", filter_endpoints_only, **kwargs)


@app.task(queue="kickoff")
def compose_planned_scan_task(**kwargs):
    urls = plannedscan.pickup(activity="scan", scanner=SCANNER_NAME, amount=kwargs.get("amount", 25))
    return compose_scan_task(urls)


def compose_manual_scan_task(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> Task:
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    if not allowed_to_scan(SCANNER_NAME):
        return group()

    kwargs = merge_endpoints_filter(STANDARD_ENDPOINT_FILTER, **kwargs)
    urls = filter_endpoints_only(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    return compose_scan_task(urls)


def compose_scan_task(urls):
    endpoints, urls_without_endpoints = retrieve_endpoints_from_urls(urls, protocols=["http", "https"], ip_versions=[4])
    endpoints = unique_and_random(endpoints)
    # remove urls that don't have the relevant endpoints anymore
    for url_id in urls_without_endpoints:
        plannedscan.finish("scan", SCANNER_NAME, url_id)
    valid_proxies = []
    proxies = ScanProxy.objects.all().filter(is_dead=False).order_by("id")[:10]
    for proxy in proxies:
        if check_proxy(proxy.as_dict()):
            valid_proxies.append(proxy.as_dict())
            # two working proxies should be enough for everyone
        if len(valid_proxies) > 1:
            break
    if not valid_proxies:
        raise SystemError("No valid proxies found for blocked endpoint test, did you configure ScanProxies?")
    log.info("Scanning for blockage on %s endpoints.", len(endpoints))
    tasks = [
        scan.si(endpoint.uri_url(), valid_proxies).set(queue=CELERY_IP_VERSION_QUEUE_NAMES[endpoint.ip_version])
        | store.s(endpoint.id)
        | plannedscan.finish.si("scan", SCANNER_NAME, endpoint.url.pk)
        for endpoint in endpoints
    ]
    return group(tasks)


@app.task()
def scan(address: str, proxies: {}) -> Dict[str, Any]:
    # attempt to contact the endpoint via a the direct connection and via a proxy.
    # note that the proxy might be ipv4 only?
    # get two or more proxies.
    with contextlib.suppress(RequestException):
        requests.head(address)
        # not blocked, so don't check via proxy
        return {
            "connects_directly": True,
            "connects_via_any_proxy": False,
            "connects_via_all_proxies": False,
            "evidence": [],
        }
    connects_via_proxy = []
    proxy_evidence = []
    for proxy in proxies:
        try:
            requests.head(
                address,
                proxies={proxy["protocol"]: proxy["address"]},
                timeout=(PROXY_NETWORK_TIMEOUT, PROXY_SERVER_TIMEOUT),
            )
            connects_via_proxy.append(True)
            proxy_evidence.append({"protocol": proxy["protocol"], "address": proxy["address"], "connects": True})
        except RequestException:
            connects_via_proxy.append(False)
            proxy_evidence.append({"protocol": proxy["protocol"], "address": proxy["address"], "connects": False})
    return {
        "connects_directly": False,
        # some proxies might not work
        "connects_via_any_proxy": any(connects_via_proxy),
        "connects_via_all_proxies": all(connects_via_proxy),
        "evidence": proxy_evidence,
    }


@app.task(queue="storage", ignore_result=True)
def store(result: dict, endpoint_id: int):
    if result["connects_directly"]:
        conclusion = FINDING_BE_REACHABLE
    elif result["connects_via_any_proxy"]:
        conclusion = FINDING_BE_BLOCKED
    else:
        conclusion = FINDING_BE_NOT_REACHABLE
    store_endpoint_scan_result(SCANNER_NAME, endpoint_id, conclusion, conclusion, result["evidence"])
