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

from websecmap.celery import EXPIRES_IN_ONE_DAY, app
from websecmap.organizations.models import Url
from websecmap.scanners import init_dict, plannedscan
from websecmap.scanners.scanner import q_configurations_to_scan, unique_and_random, url_filters
from websecmap.scanners.scanner.subdomains import discover_wildcard
from difflib import SequenceMatcher

log = logging.getLogger(__name__)

# Just changing csrf and a timestamp means a difference of just 0.9925592245505369, so 0.98 is very liberal
# Higher is more similar.
SIMILAR_CONTENT = 0.98


def filter_scan(organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs):
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)

    # Don't care about dead or not resolvable here: The subdomains below this might be very well alive.
    default_filter = {"uses_dns_wildcard": True}
    urls_filter = {**urls_filter, **default_filter}
    urls = Url.objects.all().filter(q_configurations_to_scan(level="url"), **urls_filter)
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter)
    urls = urls.only("url")

    urls = unique_and_random(urls)

    return urls


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def plan_scan(organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs):
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    urls = filter_scan(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    plannedscan.request(activity="scan", scanner="dns_clean_wildcards", urls=urls)


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def compose_planned_scan_task(**kwargs):
    urls = plannedscan.pickup(activity="scan", scanner="dns_clean_wildcards", amount=kwargs.get("amount", 25))
    return compose_scan_task(urls)


def compose_manual_scan_task(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> Task:
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    urls = filter_scan(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    return compose_scan_task(urls)


def compose_scan_task(urls: List[Url]):
    tasks = []

    for url in urls:
        tasks.append(
            get_identical_sites_on_wildcard_url.si(url.url)
            | store.s()
            | plannedscan.finish.si("scan", "dns_clean_wildcards", url.pk)
        )

    return group(tasks)


def subdomains_under_wildcard(url: str) -> List[Url]:
    result = tldextract.extract(url)
    # In this case do care about dead/not resolvable.
    # Dead will not change the state (we don't revive them)...
    # not resolvable will mean slower testing.
    return (
        Url.objects.all()
        .filter(is_dead=False, not_resolvable=False, computed_domain=result.domain, computed_suffix=result.suffix)
        .values_list("id", "url", named=True)
    )


def site_content(url) -> Dict[str, Any]:
    try:
        # Sites as deventer.nl have a different page every load.
        # Sites as hollandskroon.nl have a different page every load. So can't check that automatically.
        response = requests.get(
            f"https://{url}/",
            allow_redirects=True,
            verify=False,  # nosec: certificate validity is checked elsewhere, having some https > none
            # User agent has to be the same. It's very much possible a webserver responds differently per user agent
            # for example when seeing an outdated user agent, it might advice you to upgrade.
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/42.0.2311.135 Safari/537.36 Edge/12.246"
            },
            timeout=(30, 30),
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
    except requests.RequestException as exc:
        log.debug("Received exception on %s: %s", url, exc)
        return {
            "headers": None,
            "content": None,
            "status_code": None,
        }


def content_is_stable(url: str):
    first_run = site_content(f"{random_string()}.{url}")
    for _ in range(0, 3):
        first = first_run["content"]
        second_run = site_content(f"{random_string()}.{url}")
        second = second_run["content"]
        # None indicated no connection or another error, which means you cannot compare
        if first is None or second is None:
            log.debug("Error while retrieving page. Cannot compare.")
            return False
        match = SequenceMatcher(None, first, second)
        ratio = match.ratio()
        log.debug(f"Similarity between content is: {round(ratio * 100, 2)}%")
        if ratio < SIMILAR_CONTENT:
            return False
    return True


def random_string(length: int = 16):
    return "".join(random.choice(string.ascii_lowercase) for _ in range(length))


@app.task(queue="all_internet", expires=EXPIRES_IN_ONE_DAY)
def get_identical_sites_on_wildcard_url(wildcard_url: str) -> List[int]:
    identical = []

    if not discover_wildcard(wildcard_url):
        log.debug("No wildcard found at %s.", wildcard_url)
        return identical

    wildcard_subdomain = random_string()
    wildcard_content = site_content(f"{wildcard_subdomain}.{wildcard_url}")

    if wildcard_content == {
        "headers": None,
        "content": None,
        "status_code": None,
    }:
        # When there are errors, do not try to get subdomains.
        log.debug(
            "Wildcard retrieval for %s resulted in an error: probably wildcard not enabled. Skipping domain",
            wildcard_url,
        )
        return identical

    # could be that the wildcard renders a different page every time, in that case do not continue.
    # this happens for deventer and hollandskroon
    # Todo: it has to have a percentage similarity, so things like forgery-protection-tokens, timestamps
    # and other minor changes do not affect this scan.
    if not content_is_stable(wildcard_url):
        log.debug(
            "Address delivers a unique page every time. "
            "Therefore automatically checking for wildcards is impossible."
        )
        return identical

    subdomain_urls = subdomains_under_wildcard(wildcard_url)
    log.debug("%s has %s subdomains.", wildcard_url, len(subdomain_urls))
    for subdomain_url in subdomain_urls:

        # couldn't get the filtering correct in the subdomains_under_wildcard method.
        if subdomain_url.url == wildcard_url:
            continue

        match = SequenceMatcher(None, wildcard_content["content"], site_content(subdomain_url.url)["content"])
        ratio = match.ratio()
        log.debug("Similarity between %s and %s is: %s", wildcard_url, subdomain_url.url, round(ratio * 100, 2))
        if ratio > SIMILAR_CONTENT:
            log.debug("WILDCARD: Content of %s is the same as %s.", subdomain_url.url, wildcard_subdomain)
            identical.append(subdomain_url.id)
        else:
            log.debug("        : Content of %s differs from %s.", subdomain_url.url, wildcard_subdomain)

    log.debug("Found %s domains to be having the same data as a wildcard.", len(identical))
    return identical


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def store(url_ids: List[int]):
    for url_id in url_ids:
        url = Url.objects.all().filter(pk=url_id).first()
        if not url:
            continue
        url.is_dead = True
        url.is_dead_reason = "Same content as wildcard. So no additional value to scan."
        url.is_dead_since = datetime.now(pytz.utc)
        url.save()
