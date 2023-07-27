"""Import modules containing tasks that need to be auto-discovered by Django Celery."""
import logging

from celery import group

from websecmap.scanners import plannedscan, proxy
from websecmap.scanners.scanner_for_everything import (
    domain_to_ip,
    ip_geolocation,
    location,
    mailserver,
    ip_geolocation_correction,
)
from websecmap.scanners.scanner import (
    autoexplain_dutch_untrusted_cert,
    autoexplain_microsoft_neighboring_services,
    autoexplain_no_https_microsoft,
    autoexplain_no_https_possible,
    autoexplain_trust_microsoft,
    bannergrab_masscan,
    bannergrab_nmap,
    dns_clean_wildcards,
    dns_endpoints,
    dns_known_subdomains,
    dns_wildcards,
    dnssec,
    dummy,
    ftp,
    http,
    internet_nl_mail,
    internet_nl_web,
    nuclei_http,
    plain_http,
    ports,
    resolve_ip,
    screenshot,
    security_headers,
    subdomains,
    subdomains_amass,
    tls_qualys,
    verify_unresolvable,
    web_privacy,
    endpoint_content,
)
from websecmap.scanners.scanner import whois

log = logging.getLogger(__name__)

# explicitly declare the imported modules as this modules 'content', prevents pyflakes issues
__scanners__ = [
    dns_endpoints,
    dns_known_subdomains,
    dns_wildcards,
    dns_clean_wildcards,
    dnssec,
    dummy,
    ftp,
    http,
    internet_nl_mail,
    internet_nl_web,
    plain_http,
    screenshot,
    security_headers,
    subdomains,
    tls_qualys,
    verify_unresolvable,
    autoexplain_dutch_untrusted_cert,
    autoexplain_microsoft_neighboring_services,
    autoexplain_no_https_microsoft,
    autoexplain_trust_microsoft,
    autoexplain_no_https_possible,
    resolve_ip,
    bannergrab_masscan,
    bannergrab_nmap,
    ports,
    web_privacy,
    nuclei_http,
    subdomains_amass,
    whois,
    endpoint_content,
]

__everything__ = [domain_to_ip, ip_geolocation, location, mailserver, ip_geolocation_correction]

__others__ = [
    proxy,
    plannedscan,
]

# This is the single source of truth regarding scanner configuration.
# Lists to be used elsewhere when tasks need to be composed, these lists contain compose functions.
# Other code can iterate over these functions and call them, example: see onboard.py.
TLD_DEFAULT_EXPLORERS = []
DEFAULT_EXPLORERS = [http.compose_manual_discover_task, ftp.compose_manual_discover_task]

# Beta: dns.brute_known_subdomains_compose_task, - old code still
TLD_DEFAULT_CRAWLERS = [subdomains.compose_discover_task]
DEFAULT_CRAWLERS = []

# Beta: tls_osaft.compose_task, - is this using the outdated ssl library?
# Beta: screenshot.compose_task, - Browser is not available in docker container
DEFAULT_SCANNERS = [
    security_headers.plan_scan,
    tls_qualys.plan_scan,
    ftp.plan_scan,
    plain_http.plan_scan,
]
TLD_DEFAULT_SCANNERS = [dnssec.plan_scan]


def get_tasks(url, normal_tasks, tld_tasks):
    scanners = normal_tasks
    if url.is_top_level():
        scanners += tld_tasks

    tasks = [scanner(urls_filter={"url": url}) for scanner in scanners]
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
