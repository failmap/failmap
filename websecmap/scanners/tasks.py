"""Import modules containing tasks that need to be auto-discovered by Django Celery."""
import logging

from celery import group

from websecmap.scanners.autoexplain import autoexplain
from websecmap.scanners.scanner import (dns_endpoints, dns_wildcards, dnssec, dummy, ftp, http,
                                        internet_nl_mail, internet_nl_web, plain_http,
                                        security_headers, subdomains, tls_qualys)

log = logging.getLogger(__name__)


# explicitly declare the imported modules as this modules 'content', prevents pyflakes issues
__all__ = [tls_qualys, security_headers, dummy, http, dnssec, ftp, subdomains, internet_nl_mail, internet_nl_web,
           dns_endpoints, dns_wildcards, autoexplain]

# This is the single source of truth regarding scanner configuration.
# Lists to be used elsewhere when tasks need to be composed, these lists contain compose functions.
# Other code can iterate over these functions and call them, example: see onboard.py.
TLD_DEFAULT_EXPLORERS = []
DEFAULT_EXPLORERS = [http.compose_discover_task, ftp.compose_discover_task]

# Beta: dns.brute_known_subdomains_compose_task, - old code still
TLD_DEFAULT_CRAWLERS = [
    subdomains.compose_discover_task]
DEFAULT_CRAWLERS = []

# Beta: tls_osaft.compose_task, - is this using the outdated ssl library?
# Beta: screenshot.compose_task, - Browser is not available in docker container
DEFAULT_SCANNERS = [
    security_headers.compose_manual_scan_task,
    tls_qualys.compose_manual_scan_task,
    ftp.compose_manual_scan_task,
    plain_http.compose_manual_scan_task,
]
TLD_DEFAULT_SCANNERS = [dnssec.compose_task]


def get_tasks(url, normal_tasks, tld_tasks):
    scanners = normal_tasks
    if url.is_top_level():
        scanners += tld_tasks

    tasks = []
    for scanner in scanners:
        tasks.append(scanner(urls_filter={"url": url}))

    return group(tasks)


def explore_tasks(url):
    return get_tasks(url, DEFAULT_EXPLORERS, TLD_DEFAULT_EXPLORERS)


def crawl_tasks(url):
    return get_tasks(url, DEFAULT_CRAWLERS, TLD_DEFAULT_CRAWLERS)


def scan_tasks(url_chunk):

    tasks = []

    for scanner in DEFAULT_SCANNERS:
        # Tls qualys scans are inserted per 25. This is due to behaviour of the qualys service.
        tasks.append(scanner(urls_filter={"url__in": url_chunk}))

    # and add the top level urls.
    for url in url_chunk:
        if url.is_top_level():
            for tld_scanner in TLD_DEFAULT_SCANNERS:
                tasks.append(tld_scanner(urls_filter={"url": url}))

    return group(tasks)
