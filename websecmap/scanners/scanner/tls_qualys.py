"""
Manages endpoints:
 Protocols: https
 Ports: 443
 IP's: any related to a domain on mentioned protocols and ports.

Side effects from this scanner:
- This scanner harvests ips during scanning, which are stored as metadata.
- This scanner can discover new endpoints for port 443, protocol https, IPv4 or IPv6.
- Only urls not scanned in the past 7 days are eligible for scan.

Scans are severely rate limited using the Qualys API, trying to be as friendly as possible. If you want a faster
scan, use multiple scanners on different IP-addresses. A normal qualys scan takes about two minutes.

Be warned: the view of the internet from Qualys differs from yours. Some hosts block qualys or "foreign" traffic.

This scanner will be replaced with the O-Saft scanner when ready.

API Documentation:
https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md
"""
import ipaddress
import json
import logging
from datetime import datetime, timedelta
from multiprocessing.pool import ThreadPool
from time import sleep
from typing import List

import pytz
import requests
from celery import Task, group
from django.utils import timezone
from tenacity import RetryError, before_log, retry, wait_fixed

from websecmap.celery import app
from websecmap.organizations.models import Organization, Url
from websecmap.scanners import plannedscan
from websecmap.scanners.models import Endpoint, ScanProxy, TlsQualysScratchpad
from websecmap.scanners.proxy import (
    claim_proxy,
    release_proxy,
    service_provider_status,
    store_check_result,
    timeout_claims,
)
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.__init__ import allowed_to_scan, chunks2, q_configurations_to_scan, unique_and_random
from websecmap.scanners.scanner.http import store_url_ips

# There is a balance between network timeout and qualys result cache.
# This is relevant, since the results are not kept in cache for hours. More like 15 minutes.
API_NETWORK_TIMEOUT = 20
API_SERVER_TIMEOUT = 20

log = logging.getLogger(__name__)


"""
New architecture:
- A worker gets a set of 25 objects to scan. Will do so multithreaded,
 - - starting one every minute (or backing off if needed)
- A finished scan results in a new task (just like a scrathpad). Whenever the worker is ready all 25 scans are
  completed and the worker is ready to receive more. This is the _FASTEST_ you can ever accomplish without messy
  queue management.
"""


@app.task(queue="storage")
def plan_scan(urls_filter: dict = dict(), **kwargs):

    if not allowed_to_scan("tls_qualys"):
        return None

    # fuck the django orm, for making the following more complicated than it needs to be:
    # Plan scans for endpoints that never have been scanned
    urls = (
        Url.objects.filter(
            q_configurations_to_scan(),
            is_dead=False,
            not_resolvable=False,
            endpoint__protocol="https",
            endpoint__port=443,
            endpoint__is_dead=False,
            **urls_filter,
        )
        .exclude(
            # remove any url that has an endpoint scan on tls_qualys
            id__in=Url.objects.filter(
                is_dead=False,
                not_resolvable=False,
                endpoint__protocol="https",
                endpoint__port=443,
                endpoint__is_dead=False,
                endpoint__endpointgenericscan__type__in=[
                    "tls_qualys_encryption_quality",
                    "tls_qualys_certificate_trusted",
                ],
            )
        )
        .only("id", "url")
    )

    # Due to filtering on endpoints, the list of URLS is not distinct. We're making it so.
    plannedscan.request(activity="scan", scanner="tls_qualys", urls=unique_and_random(urls))

    # Scans for endpoints that have already been scanned:
    # Scan the bad ones more frequently than the good ones, to reduce the amount of requests.
    # todo: parameterize using settings in constance.
    parameter_sets = [
        {"exclude_urls_scanned_in_the_last_n_days": 7, "quality_levels": ["A", "A+", "A-", "trusted"]},
        {"exclude_urls_scanned_in_the_last_n_days": 3, "quality_levels": ["F", "C", "B", "not trusted"]},
    ]

    for parameter_set in parameter_sets:
        urls = Url.objects.filter(
            q_configurations_to_scan(),
            is_dead=False,
            not_resolvable=False,
            endpoint__protocol="https",
            endpoint__port=443,
            endpoint__is_dead=False,
            endpoint__endpointgenericscan__is_the_latest_scan=True,
            # an exclude filter here will not work, as you will exclude so much...
            endpoint__endpointgenericscan__last_scan_moment__lte=timezone.now()
            - timedelta(days=parameter_set["exclude_urls_scanned_in_the_last_n_days"]),
            endpoint__endpointgenericscan__rating__in=parameter_set["quality_levels"],
            **urls_filter,
        ).only("id", "url")

        plannedscan.request(activity="scan", scanner="tls_qualys", urls=unique_and_random(urls))


def compose_manual_scan_task(organizations_filter: dict = dict(), urls_filter: dict = dict(), **kwargs):
    if not allowed_to_scan("tls_qualys"):
        return group()

    # apply filter to organizations (or if no filter, all organizations)
    organizations = []
    if organizations_filter:
        organizations = Organization.objects.filter(**organizations_filter)

        # Discover Endpoints will figure out if there is https and if port 443 is open.
        # apply filter to urls in organizations (or if no filter, all urls)
        # do not scan the same url within 24 hours.
        # we assume all endpoints are scanned at the same time (this is what qualys does)

        # scan only once in seven days. an emergency fix to make sure everything is scanned.
        # todo: force re-scan, where days is < 7, with 5000 scanning takes a while and a lot still goes wrong.
        urls = (
            Url.objects.filter(
                q_configurations_to_scan(),
                is_dead=False,
                not_resolvable=False,
                endpoint__protocol="https",
                endpoint__port=443,
                endpoint__is_dead=False,
                organization__in=organizations,  # when empty, no results...
                **urls_filter,
            )
            .order_by("-endpoint__endpointgenericscan__latest_scan_moment")
            .only("id", "url")
        )
    else:
        # use order by to get a few of the most outdated results...
        urls = (
            Url.objects.filter(
                q_configurations_to_scan(),
                is_dead=False,
                not_resolvable=False,
                endpoint__protocol="https",
                endpoint__port=443,
                endpoint__is_dead=False,
                **urls_filter,
            )
            .order_by("-endpoint__endpointgenericscan__latest_scan_moment")
            .only("id", "url")
        )

    # Urls are ordered randomly.
    # Due to filtering on endpoints, the list of URLS is not distinct. We're making it so.
    urls = unique_and_random(urls)

    if not urls:
        log.warning("Applied filters resulted in no urls, thus no tls qualys tasks!")
        return group()

    log.info("Creating qualys scan task for %s urls for %s organizations.", len(urls), len(organizations))

    return compose_scan_task(urls)


@app.task(queue="storage")
def compose_planned_scan_task(**kwargs) -> Task:
    # If you run this every 10 minutes, there will be little problems with 'toctou' problems, claiming
    # a proxy is free, while it has been claimed by other results of this method (in the call before).

    if not allowed_to_scan("tls_qualys"):
        return group()

    timeout_claims()

    proxies_available = (
        ScanProxy.objects.all()
        .filter(
            is_dead=False,
            currently_used_in_tls_qualys_scan=False,
            manually_disabled=False,
            request_speed_in_ms__gte=1,
            # the upper speed should be configurable. When running N proxy checks at a time theywill be slower.
            # more checks at the same time = slower > 3000ms.
            # request_speed_in_ms__lte=2000,
        )
        .order_by("request_speed_in_ms")
    )

    # size for the proxies and such is 25 / each.
    amount_to_scan = len(proxies_available) * 25

    if not amount_to_scan:
        log.info(
            "No free proxies available for TLS qualys scans, try again later (when scans are finished or the "
            "claims on proxies have timed out."
        )
        return group()

    # using this method proxy claiming does not need to be rate limited anymore.
    urls = plannedscan.pickup(activity="scan", scanner="tls_qualys", amount=amount_to_scan)
    return compose_scan_task(urls)


def compose_scan_task(urls):

    if not urls:
        return group()

    chunks = list(chunks2(urls, 25))

    tasks = []
    for chunk in chunks:

        tasks.append(
            group(
                claim_proxy.s(chunk[0])
                | qualys_scan_bulk.s(chunk)
                | release_proxy.s(chunk[0])
                | plannedscan.finish_multiple.si("scan", "tls_qualys", chunk)
            )
        )

    return group(tasks)


# It's possible a lot of scans start at the same time. In that case the API does not have a notion of how many scans
# are running (this takes a while). This results in too many requests and still a lot of errors. To avoid that this
# method has been rate limited to one per minute per worker. This gives a bit of slack.

# Note that this is a per worker instance rate limit, and not a global rate limit.
# http://docs.celeryproject.org/en/latest/userguide/tasks.html

# scan takes about 30 minutes.
# 12 / hour = 1 every 5 minutes. In 30 minutes 6 scans will run at the same time. We used to have 10.
# 20 / hour = 1 every 3 minutes. In 30 minutes 10 scans will run at the same time.
# 30 / hours = 1 every 2 minutes. In 30 minutes 15 scans will run at the same time.
@app.task(queue="qualys", acks_late=True)
def qualys_scan_bulk(proxy: ScanProxy, urls: List[Url]):

    log.debug("Initiating bulk scan")
    log.debug("Received proxy: %s" % proxy)
    log.debug("Received urls: %s" % urls)

    # Using this all scans stay on the same server (so no ip-hopping between scans, which limits the available
    # capacity severely.
    # Using this solution still uses parallel scans, while not having to rely on the black-box of redis and celery
    # that have caused priority shifts. This is much faster and easier to understand.

    try:
        # start one every 60 seconds, a thread can manage itself if too many are running.
        pool = ThreadPool(25)

        # Even if qualys is down, it will just wait until it knows you can add more... And the retry is infinite
        # every 30 seconds. So they may be even down for a day and it will continue.
        for url in urls:

            try:
                api_results = service_provider_status(proxy)
                while api_results["max"] < 20 or api_results["this-client-max"] < 20 or api_results["current"] > 19:
                    log.debug("Running out of capacity, waiting to start new scan.")
                    sleep(70)
                    api_results = service_provider_status(proxy)

                pool.apply_async(qualys_scan_thread, [proxy, url])
                sleep(70)

            except RetryError:
                log.debug("Retry error. Could not connect to proxy anymore.")
                store_check_result.apply_async(
                    [proxy, "Retry error. Proxy died while scanning.", True, datetime.now(pytz.utc)]
                )

        pool.close()
        pool.join()

    except Exception as e:
        # catch _anything_ that goes wrong, log it to the sentry/logfile
        # This is done to still return the scanproxy so it can be released.
        log.exception(f"Unexpected crash in qualys bulk scan: {e}")

    # return the proxy so it can be closed.
    # The scan results are created as separate tasks in the scan thread.
    return proxy


# keeps scanning in a loop until it has the data to fire a
def qualys_scan_thread(proxy, url):

    normal_waiting_time = 30
    error_waiting_time = 60  # seconds until retry, can be increased when queues are full. Max = 180
    max_waiting_time = 360

    data = {}

    while True:
        try:
            api_result = service_provider_scan_via_api_with_limits(proxy, url.url)
            data = api_result["data"]
        except requests.RequestException:
            # ex: ('Connection aborted.', ConnectionResetError(54, 'Connection reset by peer'))
            # ex: EOF occurred in violation of protocol (_ssl.c:749)
            log.exception(f"(Network or Server) Error when contacting Qualys for scan on {url.url}.")
            sleep(60)
            # continue

        # Store debug data in database (this task has no direct DB access due to scanners queue).
        scratch.apply_async([url, data])
        # Always log to console. Don't ask the database (constance) if this should happen.
        report_to_console(url.url, data)

        # Qualys is already running a scan on this url
        if "status" in data:
            # Qualys has completed the scan of the url and has a result.
            if data["status"] in ["READY", "ERROR"]:
                # scan completed
                # store the result on the storage queue.
                log.debug(f"Qualys scan finished on {url.url}.")
                process_qualys_result.apply_async([data, url])
                return True
            else:
                log.debug(
                    f"Scan on {url.url} has not yet finished. "
                    f"Waiting {normal_waiting_time} seconds before next update."
                )
                sleep(normal_waiting_time)
                # Don't break out of the loop...
                # continue

        # The API is in error state, let's see if we can be nice and recover.
        if "errors" in data:
            error_message = data["errors"][0]["message"]
            # {'errors': [{'message': 'Running at full capacity. Please try again later.'}], 'status': 'FAILURE'}
            # Don't increase the amount of waiting time yet... try again in a minute.
            if error_message == "Running at full capacity. Please try again later.":
                # this happens all the time, so don't raise an exception but just make a log message.
                log.info(f"Error occurred while scanning {url.url}: qualys is at full capacity, trying later.")
                sleep(error_waiting_time)
                # Don't break out of the loop...
                # continue

            # We're going too fast with new assessments. Back off.
            if error_message.startswith("Concurrent assessment limit reached"):
                log.error(
                    f"Too many concurrent assessments: Are you running multiple scans from the same IP? "
                    f"Concurrent scans slowly lower the concurrency limit of 25 concurrent scans to zero. "
                    f"Slow down. {data['errors'][0]['message']}"
                )
                if error_waiting_time < max_waiting_time:
                    error_waiting_time += 60
                    sleep(error_waiting_time)
                    # continue

            if error_message.startswith("Too many concurrent assessments"):
                log.info(f"Error occurred while scanning {url.url}: Too many concurrent assessments.")
                if error_waiting_time < max_waiting_time:
                    error_waiting_time += 60
                    sleep(error_waiting_time)
                    # continue

            # All other situations that we did not foresee...
            log.error("Unexpected error from API on %s: %s", url.url, str(data))

        # This is an undefined state.
        # scan started without errors. It's probably pending. Reset the waiting time to 60 seconds again as we
        # we want to get the result asap.
        log.debug(f"Got to an undefined state on qualys scan on {url.url}. Scan has not finished, and we're retrying.")
        sleep(error_waiting_time)


@app.task(queue="storage")
def process_qualys_result(data, url):
    """Receive the JSON response from Qualys API, processes this result and stores it in database."""

    # log.info(data)
    # log.info(dir(data))

    # a normal completed scan.
    if data["status"] == "READY" and "endpoints" in data.keys():
        save_scan(url, data)
        return

    # missing endpoints: url propably resolves but has no TLS?
    elif data["status"] == "READY":
        scratch(url, data)
        raise ValueError("Found no endpoints in ready scan. Todo: How to handle this?")

    # Not resolving
    if data["status"] == "ERROR":
        """
        Error is usually "unable to resolve domain". Will be cleaned with endpoint discovery. It's very possible that
        the qualys scanner is blocked by the hosts. This is one of the reasons why Qualys SSL labs is not reliable.
        """
        scratch(url, data)  # we always want to see what happened.
        return


def report_to_console(domain, data):
    """
    Gives some impression of what is currently going on in the scan.

    This will show a lot of DNS messages, which means that SSL Labs is working on it.

    An error to avoid is "Too many new assessments too fast. Please slow down.", this means
    the logic to start scans is not correct (too fast) (or scans are not distributed enough).

    :param domain:
    :param data:
    :return:
    """

    status = data.get("status", "unknown")

    if status == "READY":
        for endpoint in data["endpoints"]:
            log.debug("%s (IP: %s) = %s" % (domain, endpoint["ipAddress"], endpoint.get("grade", "No TLS")))

    if status in ["DNS", "ERROR"]:
        log.debug("%s %s: Got message: %s", domain, data["status"], data.get("statusMessage", "unknown"))

    if data["status"] == "IN_PROGRESS":
        for endpoint in data["endpoints"]:
            log.debug("%s, ep: %s. status: %s" % (domain, endpoint["ipAddress"], endpoint.get("statusMessage", "0")))

    if status == "unknown":
        log.error("Unexpected data received for domain: %s, %s" % (domain, data))


# Qualys is a service that is constantly attacked / ddossed and very unreliable. So try a couple of times before
# giving up. It can even be down for half a day. Waiting a little between retries.
@retry(wait=wait_fixed(30), before=before_log(log, logging.INFO))
def service_provider_scan_via_api_with_limits(proxy, domain):
    # API Docs: https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md
    payload = {
        "host": domain,  # host that will be scanned for tls
        "publish": "off",  # will not be published on the front page of the ssllabs site
        "startNew": "off",  # that's done automatically when needed by service provider
        "fromCache": "off",  # cache can have mismatches, but is ignored when startnew. We prefer cache as the cache on
        # qualys is not long lived. We prefer it because it might give back a result faster.
        "ignoreMismatch": "on",  # continue a scan, even if the certificate is for another domain
        "all": "done",  # ?
    }

    response = requests.get(
        "https://api.ssllabs.com/api/v2/analyze",
        params=payload,
        timeout=(API_NETWORK_TIMEOUT, API_SERVER_TIMEOUT),  # 30 seconds network, 30 seconds server.
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/601.3.9 "
            "(KHTML, like Gecko) Version/9.0.2 Safari/601.3.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "DNT": "1",
        },
        proxies={proxy.protocol: proxy.address},
        cookies={},
    )

    # log.debug(vars(response))  # extreme debugging
    log.debug(
        "Assessments: max: %s, current: %s, this client: %s, this: %s, proxy: %s",
        response.headers.get("X-Max-Assessments", 25),
        response.headers.get("X-Current-Assessments", 0),
        response.headers.get("X-ClientMaxAssessments", 25),
        domain,
        proxy,
    )

    return {
        "max": int(response.headers.get("X-Max-Assessments", 25)),
        "current": int(response.headers.get("X-Current-Assessments", 0)),
        "this-client-max": int(response.headers.get("X-ClientMaxAssessments", 25)),
        "data": response.json(),
    }


def save_scan(url, data):
    """
    When a scan is ready it can contain both ipv4 and ipv6 endpoints. Sometimes multiple of both.

    :param url:
    :param data: raw JSON data from qualys
    :return:
    """

    log.debug("Saving scan for %s", url.url)

    # this scanner only does https/443, so there are two possible entry points for a domain:
    stored_ipv6 = False
    stored_ipv4 = False

    log.debug(f"Found {len(data['endpoints'])} endpoints in data.")

    # Scan can contain multiple IPv4 and IPv6 endpoints, for example, four of each.
    for qualys_endpoint in data["endpoints"]:
        """
        qep['grade']  # T, if trust issues.
        qep['gradeTrustIgnored']  # A+ to F
        """

        # Prevent storage of more than one result for either IPv4 and IPv6.
        if stored_ipv6 and ":" in qualys_endpoint["ipAddress"]:
            continue

        if stored_ipv4 and ":" not in qualys_endpoint["ipAddress"]:
            continue

        if ":" in qualys_endpoint["ipAddress"]:
            stored_ipv6 = True
            ip_version = 6
        else:
            stored_ipv4 = True
            ip_version = 4
        # End prevent duplicates

        message = qualys_endpoint["statusMessage"]
        log.debug(f"Message for endpoint {qualys_endpoint['ipAddress']} is {message}.")

        # Qualys might discover endpoints we don't have yet. In that case, be pragmatic and create the endpoint.
        failmap_endpoint = Endpoint.force_get(url, ip_version, "https", 443)

        if message in [
            "Unable to connect to the server",
            "Failed to communicate with the secure server",
            "Unexpected failure",
            "Failed to obtain certificate",
            "IP address is from private address space (RFC 1918)",
            "No secure protocols supported",
            "Certificate not valid for domain name",
        ]:
            # Note: Certificate not valid for domain name can be ignored with correct API setting.
            # Nothing to store: something went wrong at the API side and we can't fix that.
            # Example; werkplek.alkmaar.nl, cannot be scanned with this scanner, and will result in an error.
            # make sure that the newest scan result is then error, so we can handle it properly in the report.
            # this server DOES respond on ipv6, but not on ipv4. Creating a very old, and never deleted ipv4 endpoint.
            # even worse: the http verify scanner sees that it exists, and if you type it in in the browser, it
            # does exist. So perhaps they blocked the qualys scanner, which is perfectly possible of course.
            store_endpoint_scan_result("tls_qualys_certificate_trusted", failmap_endpoint, "scan_error", message)
            store_endpoint_scan_result("tls_qualys_encryption_quality", failmap_endpoint, "scan_error", message)
            continue

        if message not in ["Ready"]:
            continue

        rating = qualys_endpoint["grade"]
        rating_no_trust = qualys_endpoint["gradeTrustIgnored"]

        if rating == "T":
            trust = "not trusted"
        else:
            trust = "trusted"

        store_endpoint_scan_result("tls_qualys_certificate_trusted", failmap_endpoint, trust, "")
        store_endpoint_scan_result("tls_qualys_encryption_quality", failmap_endpoint, rating_no_trust, "")

    # Store IP address of the scan as metadata
    ips = [ipaddress.ip_address(endpoint["ipAddress"]).compressed for endpoint in data["endpoints"]]
    store_url_ips(url, ips)
    return


@app.task(queue="storage")
def scratch(domain, data):
    log.debug("Scratching data for %s", domain)
    scratchpad = TlsQualysScratchpad()
    scratchpad.domain = domain
    scratchpad.data = json.dumps(data)
    scratchpad.save()
