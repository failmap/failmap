"""
Wildcard domains and services result in non-trusted certificates and a lot of unneeded domains.

This feature retrieves all wildcard domains from the database and will attempt to discover if the wildcard
site content matches a domain of that address. If that's the case, the url is marked as dead due to it going
to the same stuff as a regular wildcard page.
"""
import logging
import random
import string
from datetime import datetime
from typing import Any, Dict, List

import pytz
import requests
import tldextract
from celery import Task, group

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners import plannedscan
from websecmap.scanners.scanner import q_configurations_to_scan, unique_and_random, url_filters
from websecmap.scanners.scanner.http import get_random_user_agent
from websecmap.scanners.scanner.subdomains import discover_wildcard

log = logging.getLogger(__name__)


def filter_scan(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
):
    # Don't care about dead or not resolvable here: The subdomains below this might be very well alive.
    default_filter = {"uses_dns_wildcard": True}
    urls_filter = {**urls_filter, **default_filter}
    urls = Url.objects.all().filter(q_configurations_to_scan(level="url"), **urls_filter)
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter)
    urls = urls.only("url")

    urls = unique_and_random(urls)

    return urls


@app.task(queue="storage")
def plan_scan(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
):

    urls = filter_scan(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    plannedscan.request(activity="scan", scanner="dns_clean_wildcards", urls=urls)


@app.task(queue="storage")
def compose_planned_scan_task(**kwargs):
    urls = plannedscan.pickup(activity="scan", scanner="dns_clean_wildcards", amount=kwargs.get("amount", 25))
    return compose_scan_task(urls)


def compose_manual_scan_task(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
) -> Task:
    urls = filter_scan(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    return compose_scan_task(urls)


def compose_scan_task(urls):
    tasks = []

    for url in urls:
        tasks.append(
            get_identical_sites_on_wildcard_url.si(url)
            | store.s()
            | plannedscan.finish.si("scan", "dns_clean_wildcards", url)
        )

    return group(tasks)


def subdomains_under_wildcard(url: Url) -> List[Url]:
    result = tldextract.extract(url.url)
    # In this case do care about dead/not resolvable.
    # Dead will not change the state (we don't revive them)...
    # not resolvable will mean slower testing.
    return list(
        Url.objects.all().filter(
            is_dead=False, not_resolvable=False, computed_domain=result.domain, computed_suffix=result.suffix
        )
    )


def site_content(url) -> Dict[str, Any]:
    try:
        # Sites as deventer.nl have a different page every load.
        # Sites as hollandskroon.nl have a different page every load. So can't check that automatically.
        response = requests.get(
            f"https://{url}/",
            allow_redirects=True,
            verify=False,  # certificate validity is checked elsewhere, having some https > none
            headers={"User-Agent": get_random_user_agent()},
            timeout=(3, 3),
        )
        # remove timestamps from headers, and also include header hash in response.
        # dates are always unique if we check it later...
        if "Date" in response.headers:
            del response.headers["Date"]
        if "date" in response.headers:
            del response.headers["date"]
        return {
            "headers": response.headers,
            "content": response.content,
            "status_code": response.status_code,
        }
    except requests.RequestException:
        return {
            "headers": None,
            "content": None,
            "status_code": None,
        }


@app.task(queue="all_internet")
def get_identical_sites_on_wildcard_url(wildcard_url: Url) -> List[Url]:
    identical = []

    if not discover_wildcard(wildcard_url.url):
        return identical

    wildcard_subdomain = "".join(random.choice(string.ascii_lowercase) for i in range(16))
    wildcard_content = site_content(f"{wildcard_subdomain}.{wildcard_url.url}")

    if wildcard_content == {
        "headers": None,
        "content": None,
        "status_code": None,
    }:
        # When there are errors, do not try to get subdomains.
        log.debug(f"{wildcard_url} resulted in an error, skipping.")
        return identical

    # could be that the wildcard renders a different page every time, in that case do not continue.
    # this happens for deventer and hollandskroon
    wildcard_content2 = site_content(f"{wildcard_subdomain}.{wildcard_url.url}")
    wildcard_content3 = site_content(f"{wildcard_subdomain}.{wildcard_url.url}")
    wildcard_content4 = site_content(f"{wildcard_subdomain}.{wildcard_url.url}")

    if not all(element == wildcard_content for element in [wildcard_content2, wildcard_content3, wildcard_content4]):
        log.debug(
            "Address delivers a unique page every time. Therefore automatically checking for wildcards is impossible."
        )
        return identical

    subdomain_urls = subdomains_under_wildcard(wildcard_url)
    log.debug(f"{wildcard_url} has {len(subdomain_urls)} subdomains.")
    for subdomain_url in subdomain_urls:

        # couldn't get the filtering correct in the subdomains_under_wildcard method.
        if subdomain_url == wildcard_url:
            continue

        # Not needed: in this case the www. is the same as the (steady) wildcard. And thus is also not useful.
        # Don't remove the www. prefix subdomain of the 2nd level domain, that domain is
        # intended to be the same as the 2nd level domain.
        # if subdomain_url.url == f"www.{wildcard_url.url}":
        #     log.debug(f"Will keep {subdomain_url.url} as that is intended to be the same as {wildcard_url.url}")
        #     continue

        subdomain_content = site_content(subdomain_url.url)
        if wildcard_content == subdomain_content:
            log.debug(f"WILDCARD: Content of {subdomain_url} is the same as {wildcard_subdomain}.")
            identical.append(subdomain_url)
        else:
            log.debug(f"        : Content of {subdomain_url} differs from {wildcard_subdomain}.")

    return identical


@app.task(queue="storage")
def store(urls: List[Url]):
    log.debug(f"Received {len(urls)} that have been found to be having the same data as a wildcard.")

    for url in urls:
        url.is_dead = True
        url.is_dead_reason = "Same content as wildcard. So no additional value to scan."
        url.is_dead_since = datetime.now(pytz.utc)
        url.save()
