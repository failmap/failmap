"""Import modules containing tasks that need to be auto-discovered by Django Celery."""

import logging

from websecmap.scanners import plannedscan, progress_regress_results, proxy

# todo: iterate over scanners as tasks are often forgotten
from websecmap.scanners.scanner import (
    autoexplain_dane_microsoft,
    autoexplain_dutch_untrusted_cert,
    autoexplain_microsoft_neighboring_services,
    autoexplain_no_https_microsoft,
    autoexplain_no_https_possible,
    autoexplain_trust_microsoft,
    bannergrab_masscan,
    bannergrab_nmap,
    blocked_endpoint,
    cookie_consent,
    dns_clean_wildcards,
    dns_endpoints,
    dns_known_subdomains,
    dns_wildcards,
    dnssec,
    dummy,
    endpoint_headers,
    # explicitly disabled as these tasks take an infinite amount of time until refactoring; endpoint_content,
    # endpoint_content,
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
    whois,
)
from websecmap.scanners.scanner_for_everything import (
    domain_to_ip,
    ip_geolocation,
    ip_geolocation_correction,
    locate_and_correct,
    location,
    mailserver,
)

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
    autoexplain_dane_microsoft,
    resolve_ip,
    bannergrab_masscan,
    bannergrab_nmap,
    ports,
    web_privacy,
    nuclei_http,
    subdomains_amass,
    whois,
    endpoint_headers,
    cookie_consent,
    blocked_endpoint,
]

__everything__ = [
    domain_to_ip,
    ip_geolocation,
    location,
    mailserver,
    ip_geolocation_correction,
    locate_and_correct,
    progress_regress_results,
]

__others__ = [
    proxy,
    plannedscan,
]
