"""
It separates the scans as it might be desirable to use different scanners.

Todo: the list of known subdomains might help (a lot) with breaking nsec3 hashes?
https://github.com/anonion0/nsec3map

"""


import logging

from celery import Task, group

from websecmap.celery import app
from websecmap.scanners import plannedscan
from websecmap.scanners.scanner.__init__ import allowed_to_discover_urls, unique_and_random
from websecmap.scanners.scanner.subdomains import (
    url_by_filters,
    wordlist_scan,
    get_popular_subdomains,
    dnsrecon_parse_report_contents,
)

log = logging.getLogger(__package__)


def filter_discover(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
):

    urls = url_by_filters(organizations_filter=organizations_filter, urls_filter=urls_filter)
    return unique_and_random(urls)


@app.task(queue="storage")
def compose_planned_discover_task(**kwargs):
    urls = plannedscan.pickup(activity="discover", scanner="dns_known_subdomains", amount=kwargs.get("amount", 25))
    return compose_discover_task(urls)


@app.task(queue="storage")
def plan_discover(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
):

    if not allowed_to_discover_urls("dns_known_subdomains"):
        return group()

    urls = filter_discover(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    plannedscan.request(activity="discover", scanner="dns_known_subdomains", urls=urls)


def compose_discover_task(urls):
    if not urls:
        return group()

    first_url = urls[0]
    first_organization = first_url.organization.all().first()

    # The country is more then enough to get a sort of feasible list of subdomains.
    wordlist = get_popular_subdomains(first_organization.country.code)

    # The worker has no way to write / save things. A wordlist can be 10's of thousands of words.
    task = group(
        wordlist_scan.si(url.url, wordlist)
        | dnsrecon_parse_report_contents.s(url.as_dict())
        | plannedscan.finish.si("discover", "dns_known_subdomains", url.pk)
        for url in urls
    )
    return task


def compose_manual_discover_task(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
) -> Task:

    if not allowed_to_discover_urls("dns_known_subdomains"):
        return group()

    urls = filter_discover(organizations_filter, urls_filter, endpoints_filter, **kwargs)

    # a heuristic
    if not urls:
        log.info("Did not get any urls to discover known subdomains.")
        return group()

    log.debug("Going to scan subdomains for the following %s urls." % len(urls))

    return compose_discover_task(urls)
