"""
Performs a range of DNS scans:
- Using Search engines
- Using Wordlists
- Using Certificate Transparency
- Using NSEC

It separates the scans as it might be desirable to use different scanners.

Todo: the list of known subdomains might help (a lot) with breaking nsec3 hashes?
https://github.com/anonion0/nsec3map

"""
# todo: if ScannerHttp.has_internet_connection():
# todo: language matters, many of the NL subdomains don't make sense in other countries.

import logging

from celery import Task, group

from websecmap.scanners.scanner.dns import get_subdomains, url_by_filters, wordlist_scan
from websecmap.scanners.scanner.scanner import allowed_to_discover

log = logging.getLogger(__package__)


def compose_discover_task(organizations_filter: dict = dict(),
                          urls_filter: dict = dict(),
                          endpoints_filter: dict = dict(), **kwargs) -> Task:

    if not allowed_to_discover("brute_known_subdomains_compose_task"):
        return group()

    urls = url_by_filters(organizations_filter=organizations_filter,
                          urls_filter=urls_filter,
                          endpoints_filter=endpoints_filter)

    # a heuristic
    if not urls:
        log.info("Did not get any urls to discover known subdomains.")
        return group()

    # Remove all urls that should not have
    urls = [url for url in urls if not url.do_not_find_subdomains]

    log.debug("Going to scan subdomains for the following %s urls." % len(urls))

    first_url = urls[0]
    first_organization = first_url.organization.all().first()

    # The country is more then enough to get a sort of feasible list of subdomains.
    wordlist = get_subdomains([first_organization.country], None)

    # The worker has no way to write / save things. A wordlist can be 10's of thousands of words.
    task = group(wordlist_scan.si([url], wordlist) for url in urls)
    return task
