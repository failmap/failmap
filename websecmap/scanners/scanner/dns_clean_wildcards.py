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
from typing import List

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


def site_content(url) -> str:
    # Attempt cleanup on both http and https. It kills the url, not endpoints, so any http or https is fine (sort of)
    # Having wildcard on https and not on http is not possible since wilcards happen at dns level
    try:
        data = site_content_request(f"https://{url}")
        return data
    except requests.RequestException:
        try:
            data = site_content_request(f"http://{url}")  # noqa
            return data
        except requests.RequestException as exc:
            log.debug(exc)
            return "[ERROR]"


def site_content_request(full_url) -> str:
    # Sites as deventer.nl have a different page every load.
    # Sites as hollandskroon.nl have a different page every load. So can't check that automatically.
    response = requests.get(
        f"{full_url}/",
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

    return response.text


def content_is_stable(url: str):
    first_run = site_content(f"{random_string()}.{url}")
    for _ in range(0, 3):
        second_run = site_content(f"{random_string()}.{url}")
        # None indicated no connection or another error, which means you cannot compare
        if first_run is None or second_run is None:
            log.debug("Error while retrieving page. Cannot compare.")
            return False
        match = SequenceMatcher(None, first_run, second_run)
        ratio = match.ratio()
        log.debug(f"Similarity between content is: {round(ratio * 100, 2)}%")
        if ratio < SIMILAR_CONTENT:
            return False
    return True


def random_string(length: int = 16):
    return "".join(random.choice(string.ascii_lowercase) for _ in range(length))


@app.task(queue="all_internet", expires=EXPIRES_IN_ONE_DAY)
def get_identical_sites_on_wildcard_url(wildcard_url: str) -> List[int]:

    if not discover_wildcard(wildcard_url):
        log.debug("No wildcard found at %s.", wildcard_url)
        return []

    if not content_is_stable(wildcard_url):
        log.debug("Address delivers a unique page every time. Checking for wildcards is impossible.")
        return []

    random_data = random_string()
    wildcard_content = site_content(f"{random_data}.{wildcard_url}")
    if wildcard_content == "[ERROR]":
        log.debug("Wildcard retrieval for %s resulted in an error. Skipping domain", wildcard_url)
        return []

    identical = []
    for subdomain in subdomains_under_wildcard(wildcard_url):

        # couldn't get the filtering correct in the subdomains_under_wildcard method.
        if subdomain.url == wildcard_url:
            continue

        ratio = SequenceMatcher(None, wildcard_content, site_content(subdomain.url)).ratio()
        log.debug(
            "%s similarity between %s.%s and %s.", round(ratio * 100, 2), random_data, wildcard_url, subdomain.url
        )
        if ratio > SIMILAR_CONTENT:
            identical.append(subdomain.id)

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
