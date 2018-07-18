"""Import modules containing tasks that need to be auto-discovered by Django Celery."""

from celery import group

from . import (scanner_dns, scanner_dnssec, scanner_dummy, scanner_ftp, scanner_http,
               scanner_plain_http, scanner_screenshot, scanner_security_headers, scanner_tls_osaft,
               scanner_tls_qualys)

# explicitly declare the imported modules as this modules 'content', prevents pyflakes issues
__all__ = [scanner_tls_qualys, scanner_security_headers, scanner_dummy, scanner_http, scanner_dnssec, scanner_ftp,
           scanner_tls_osaft, scanner_screenshot]

# This is the single source of truth regarding scanner configuration.
# Lists to be used elsewhere when tasks need to be composed, these lists contain compose functions.
# Other code can iterate over these functions and call them, example: see onboard.py.
TLD_DEFAULT_EXPLORERS = []
DEFAULT_EXPLORERS = [scanner_http.compose_task, scanner_ftp.compose_discover_task]

TLD_DEFAULT_CRAWLERS = [
    scanner_dns.brute_known_subdomains_compose_task,
    scanner_dns.certificate_transparency_compose_task,
    scanner_dns.nsec_compose_task]
DEFAULT_CRAWLERS = []

DEFAULT_SCANNERS = [
    scanner_plain_http.compose_task,
    scanner_security_headers.compose_task,
    scanner_tls_qualys.compose_task,
    scanner_tls_osaft.compose_task,
    scanner_ftp.compose_task,
    scanner_screenshot.compose_task
]
TLD_DEFAULT_SCANNERS = [scanner_dnssec.compose_task]


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
