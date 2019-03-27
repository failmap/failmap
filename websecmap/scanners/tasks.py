"""Import modules containing tasks that need to be auto-discovered by Django Celery."""
import datetime
import logging
from typing import List

import requests
from celery import group

from websecmap.celery import app
from websecmap.scanners.models import ScanProxy
from websecmap.scanners.scanner import (dnssec, dummy, ftp, http, internet_nl_mail, internet_nl_web,
                                        plain_http, security_headers, subdomains, tls_qualys)
from websecmap.scanners.scanner.tls_qualys import check_proxy

log = logging.getLogger(__name__)


# explicitly declare the imported modules as this modules 'content', prevents pyflakes issues
__all__ = [tls_qualys, security_headers, dummy, http, dnssec, ftp, subdomains, internet_nl_mail, internet_nl_web]

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


@app.task(queue='storage')
def import_proxies_by_country(countries: List = [], amount=100, **kwargs):
    """
    Proxies are retrieved per 50. We only want https proxies at the moment.

    :param countries:
    :return:
    """

    if not countries:
        countries = ["NL", "DE", "BE", "SE", "FR"]

    log.debug("Going to import proxies from %s" % countries)

    # ours:   1547644379
    # ours2:  1547645865107.048
    # theirs: 1547643411986
    # have to add some extra values it seems...
    timestamp = round(datetime.datetime.now().timestamp() * 1000)

    proxies = []
    for country in countries:
        for skip in range(0, amount, 50):
            log.debug("Getting proxies for %s %s %s" % (country, skip, timestamp))
            try:
                response = requests.get(
                    "https://api.openproxy.space/short/country/%s?limit=50&skip=%s&ts=%s" % (country, skip, timestamp))

                result = response.json()
            except BaseException:
                break

            # error, nothing left
            if "status" in result:
                log.debug("Status returned: %s" % result['status'])
                break

            # more proxies.
            proxies += result
            log.debug("Currently having %s proxies listed." % len(proxies))

    # filtering out proxies per protocol. We don't need socks, http etc... only https.
    proxies_with_https = [proxy for proxy in proxies if "https" in proxy['protocols']]

    log.debug("There are %s proxies in this list that support https." % len(proxies_with_https))

    # add the new proxies.
    for proxy in proxies_with_https:

        address = "%s:%s" % (proxy['ip'], proxy['port'])

        if ScanProxy.objects.all().filter(address=address).exists():
            log.debug("Proxy with address %s already exists, skipping." % address)
            continue

        new_proxy = ScanProxy()
        new_proxy.protocol = "https"
        new_proxy.address = address
        new_proxy.save()
        log.debug("Added proxy with address %s" % address)

        # also kick off a test for the proxy to see if it still functions
        check_proxy.apply_async([new_proxy])


@app.task(queue='storage')
def check_existing_alive_proxies():

    proxies = ScanProxy.objects.all().filter(
        is_dead=False,
        manually_disabled=False,
    )

    for proxy in proxies:
        check_proxy.apply_async([proxy])
