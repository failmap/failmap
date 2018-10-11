"""Import modules containing tasks that need to be auto-discovered by Django Celery."""

from celery import group

from failmap.scanners.scanner import (dns, dnssec, dummy, ftp, http, plain_http, screenshot,
                                      security_headers, tls_osaft, tls_qualys)

# explicitly declare the imported modules as this modules 'content', prevents pyflakes issues
__all__ = [tls_qualys, security_headers, dummy, http, dnssec, ftp, tls_osaft, screenshot, dns]

# This is the single source of truth regarding scanner configuration.
# Lists to be used elsewhere when tasks need to be composed, these lists contain compose functions.
# Other code can iterate over these functions and call them, example: see onboard.py.
TLD_DEFAULT_EXPLORERS = []
DEFAULT_EXPLORERS = [http.compose_discover_task, ftp.compose_discover_task]

# Beta: dns.brute_known_subdomains_compose_task, - old code still
TLD_DEFAULT_CRAWLERS = [
    dns.certificate_transparency_compose_task,
    dns.nsec_compose_task]
DEFAULT_CRAWLERS = []

# Beta: tls_osaft.compose_task, - is this using the outdated ssl library?
# Beta: screenshot.compose_task, - Browser is not available in docker container
DEFAULT_SCANNERS = [
    security_headers.compose_task,
    tls_qualys.compose_task,
    ftp.compose_task,
    plain_http.compose_task,
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


def scan_tasks(url):
    return get_tasks(url, DEFAULT_SCANNERS, TLD_DEFAULT_SCANNERS)
