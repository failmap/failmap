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
import json
import logging
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError
from multiprocessing.pool import ThreadPool
from time import sleep
from typing import Any, Dict, List

import requests
from celery import Task, group
from tenacity import RetryError, before_log, retry, wait_fixed

from websecmap.celery import app
from websecmap.organizations.models import Organization, Url
from websecmap.scanners import init_dict, plannedscan
from websecmap.scanners.models import Endpoint, ScanProxy, TlsQualysScratchpad, EndpointGenericScan
from websecmap.scanners.proxy import (
    claim_proxy,
    release_proxy,
    service_provider_status,
    store_check_result,
    timeout_claims,
)
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.__init__ import allowed_to_scan, chunks2, q_configurations_to_scan, unique_and_random

# There is a balance between network timeout and qualys result cache.
# This is relevant, since the results are not kept in cache for hours. More like 15 minutes.
from websecmap.scanners.scanner.http import force_get_endpoint

API_NETWORK_TIMEOUT = 30
API_SERVER_TIMEOUT = 30

log = logging.getLogger(__name__)


"""
New architecture:
- A worker gets a set of 25 objects to scan. Will do so multithreaded,
 - - starting one every minute (or backing off if needed)
- A finished scan results in a new task (just like a scrathpad). Whenever the worker is ready all 25 scans are
  completed and the worker is ready to receive more. This is the _FASTEST_ you can ever accomplish without messy
  queue management.
"""


def filter_scan(organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs):
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    if organizations_filter:
        organizations = Organization.objects.filter(**organizations_filter).only("id")
        urls = Url.objects.filter(q_configurations_to_scan(), organization__in=organizations, **urls_filter)
    else:
        urls = Url.objects.filter(q_configurations_to_scan(), **urls_filter)

    # We only perform an IN query, and need nothing of these urls except the ID:
    urls = urls.only("id")

    # select endpoints to scan based on filters
    endpoints = Endpoint.objects.filter(
        # apply filter to endpoints (or if no filter, all endpoints)
        url__in=urls,
        url__is_dead=False,
        url__not_resolvable=False,
        is_dead=False,
        port=443,
        protocol="https",
        **endpoints_filter,
    ).only("id", "port", "protocol", "ip_version", "url__id", "url__url")

    # unique endpoints only
    endpoints = unique_and_random(endpoints)
    return unique_and_random([endpoint.url for endpoint in endpoints])


@app.task(queue="kickoff", ignore_result=True)
def plan_scan(organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs):
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    if not allowed_to_scan("tls_qualys"):
        return group()

    urls = filter_scan(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    plannedscan.request(activity="scan", scanner="tls_qualys", urls=urls)
    return group()


@app.task(queue="kickoff", ignore_result=True)
def plan_scan_optimized():
    """
    There are all kinds of optimizations in this task due to scanning as few urls as possible.
    - Scanning once every 7 days if everything was OK and scanning once every 3 days in case of errors.
    - This increases complexity and causes confusion for requesting re-scans.

    """

    if not allowed_to_scan("tls_qualys"):
        return

    # While technically it's possible to plan scans on endpoints/urls that have never been scanned, the query
    # created is 100% correct and takes over 1.5 hours. Causing tasks to restart and thus creating ANOTHER
    # query and so on. Instead of this correct query we just plan scans on urls that have been recently added.
    # eg in the last week or so. Given this routine is called every 3 days this will cause a slight duplication.
    # down side: when the method is not called every 3 days some urls will never be scanned for the first time.
    urls = Url.objects.filter(
        q_configurations_to_scan(),
        is_dead=False,
        not_resolvable=False,
        endpoint__protocol="https",
        endpoint__port=443,
        endpoint__is_dead=False,
        created_on__gte=datetime.now() - timedelta(days=14),
    )

    # here is the slow and correct approach preserved for when someone thinks they can do it better :)
    # urls = (
    #     Url.objects.filter(
    #         q_configurations_to_scan(),
    #         is_dead=False,
    #         not_resolvable=False,
    #         endpoint__protocol="https",
    #         endpoint__port=443,
    #         endpoint__is_dead=False,
    #         **urls_filter,
    #     )
    #     .exclude(
    #         # remove any url that has an endpoint scan on tls_qualys
    #         id__in=Url.objects.filter(
    #             is_dead=False,
    #             not_resolvable=False,
    #             endpoint__protocol="https",
    #             endpoint__port=443,
    #             endpoint__is_dead=False,
    #             endpoint__endpointgenericscan__type__in=[
    #                 "tls_qualys_encryption_quality",
    #                 "tls_qualys_certificate_trusted",
    #             ],
    #         )
    #     )
    #     .only("id", "url")
    # )

    # Due to filtering on endpoints, the list of URLS is not distinct. We're making it so.
    log.debug(f"1: planning {len(urls)} scans that have not been scanned yet.")
    plannedscan.request(activity="scan", scanner="tls_qualys", urls=unique_and_random(urls))

    # These are the ones you definitely need to scan to figure out what the state is.
    # It's desired to update them as their score negatively affects their color on the site.
    urls = Url.objects.filter(
        q_configurations_to_scan(),
        is_dead=False,
        not_resolvable=False,
        endpoint__protocol="https",
        endpoint__port=443,
        endpoint__is_dead=False,
        endpoint__endpointgenericscan__is_the_latest_scan=True,
        # an exclude filter here will not work, as you will exclude so much...
        # as we're not using parameter sets anymore, there is no use in filtering days since last scan.
        # endpoint__endpointgenericscan__last_scan_moment__lte=datetime.now(timezone.utc) - timedelta(days=0),
        endpoint__endpointgenericscan__rating__in=["F", "C", "B", "not trusted"],
    ).only("id", "url")
    log.debug(f"2: planning {len(urls)} scans that are F/C/V=B or not_trusted.")
    plannedscan.request(activity="scan", scanner="tls_qualys", urls=unique_and_random(urls))

    # Now for the bit more complex part: only scan the A/A+/A- / trusted if they are about to expire.
    # todo: you do not need to plan a scan for endpoints that are A/A+/A- or trusted every few days.
    # So before starting a scan, check if the certificate is within 10 days of expiring. In that case start a
    # scan. This significantly reduces the amount of requests per month. Large problem is that the evidence column
    # is not JSON yet, meaning we have to do some trickery to get the notafter date.
    # example evidence:
    """
    evidence = [
      {
        "subject": "CN=mijn-acc.groningen.nl",
        "commonNames": [
          "mijn-acc.groningen.nl"
        ],
        "altNames": [
          "mijn-acc.groningen.nl"
        ],
        "notBefore": 1702015407000,
        "notAfter": 1709791406000,
        "issuerSubject": "CN=R3, O=Let's Encrypt, C=US",
        "issuerLabel": "R3",
        "sigAlg": "SHA256withRSA",
        "revocationInfo": 2,
        "crlURIs": [
          ""
        ],
        "ocspURIs": [
          "http://r3.o.lencr.org"
        ],
        "revocationStatus": 2,
        "crlRevocationStatus": 4,
        "ocspRevocationStatus": 2,
        "sgc": 0,
        "issues": 0,
        "sct": true,
        "mustStaple": 0,
        "sha1Hash": "c1f3b82b761a15945ab991ae4900bc10e65edbd8",
        "pinSha256": "6I/tDtpbWLgfvO5R4h05wGIj6KbRr61IwOkd9GqjkrI="
      }
    ]

    The evidence is only stored at tls_qualys_certificate_trusted, and there are situation where the encryption quality
    is A, A+, A-. But tls_qualys_certificate_trusted is available at every scan. Meaning just walk through those
    and skip those which have a bad rating which would have been scanned again above.

    in this case we want to know what the rating is from the paired metric, and only if it is A+, A- or A then
    see if it should be renewed soon, and then request a rescan.
    """
    epgs = EndpointGenericScan.objects.filter(
        q_configurations_to_scan(level="endpoint_generic_scan"),
        endpoint__url__is_dead=False,
        endpoint__url__not_resolvable=False,
        endpoint__protocol="https",
        endpoint__port=443,
        endpoint__is_dead=False,
        is_the_latest_scan=True,
        rating__in=["trusted"],
    )
    # now figure out which ones are within 10 days of expiring. Only request those to be scanned.
    additional_urls_to_scan = set()
    log.debug("Found %s endpoint_generic_scans", epgs.count())
    for scan in epgs:
        try:
            matching_scan = (
                EndpointGenericScan.objects.filter(
                    endpoint=scan.endpoint,
                    is_the_latest_scan=True,
                    type="tls_qualys_encryption_quality",
                )
                .order_by("-id")
                .first()
            )
            # no matching scan, which is weird, make sure to scan again.
            if not matching_scan:
                log.debug("No matching scan found for url id: %s", scan.endpoint.url.id)
                raise ValueError("")

            rating_of_quality_scan = matching_scan.rating
            # all other ratings have already been requested.
            if rating_of_quality_scan not in ["A", "A+", "A-"]:
                log.debug("No matching scan found for url: id %s", scan.endpoint.url.id)
                continue

            # 1709791406000
            evidence_of_trust_scan = json.loads(scan.evidence)
            if len(evidence_of_trust_scan) == 0:
                # no evidence was saved. Rescan
                additional_urls_to_scan.add(scan.endpoint.url)
                continue

            if "notAfter" not in evidence_of_trust_scan[0]:
                # no correct scan data was saved. Rescan.
                additional_urls_to_scan.add(scan.endpoint.url)
                continue

            notafter = evidence_of_trust_scan[0]["notAfter"]
            datetime_of_notafter = datetime.fromtimestamp(notafter, timezone.utc)
            if datetime_of_notafter < datetime.now(timezone.utc) - timedelta(days=10):
                log.debug(f"3: planning url id: {scan.endpoint.url.id} because the cert will expire within 10 days.")
                log.debug(f" {datetime_of_notafter} {datetime.now(timezone.utc) - timedelta(days=10)}")
                additional_urls_to_scan.add(scan.endpoint.url)
            else:
                log.debug(f"skipping url id: {scan.endpoint.url.id} because it is not within 10 days.")
                # prevent that scan looks outdated on the map.
                scan.last_scan_moment = datetime.now(timezone.utc)
                scan.save(update_fields=["last_scan_moment"])

        except (JSONDecodeError, ValueError):
            log.debug("4: Json decode error for url id: %s", scan.endpoint.url.id)
            # failed to load, so make sure there will be a new scan with proper evidence.
            additional_urls_to_scan.add(scan.endpoint.url)

    plannedscan.request(activity="scan", scanner="tls_qualys", urls=unique_and_random(list(additional_urls_to_scan)))


def compose_manual_scan_task(organizations_filter: dict = None, urls_filter: dict = None, **kwargs):
    if not allowed_to_scan("tls_qualys"):
        return group()

    organizations_filter, urls_filter = init_dict(organizations_filter, urls_filter)

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
            .order_by("-endpoint__endpointgenericscan__last_scan_moment")
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
            .order_by("-endpoint__endpointgenericscan__last_scan_moment")
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


@app.task(queue="kickoff")
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


def compose_scan_task(urls: List[Url]) -> Task:
    if not urls:
        return group()

    chunks = list(chunks2(urls, 25))

    tasks = []
    for chunk in chunks:
        tracing_label = chunk[0].url

        chunk_as_ids = [url.pk for url in chunk]
        chunk_as_urls = [url.url for url in chunk]

        tasks.append(
            group(
                claim_proxy.s(tracing_label)
                | qualys_scan_bulk.s(chunk_as_urls)
                | release_proxy.s(tracing_label)
                | plannedscan.finish_multiple.si("scan", "tls_qualys", chunk_as_ids)
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
def qualys_scan_bulk(proxy: Dict[str, Any], urls: List[str]):
    log.debug("Initiating bulk scan")
    log.debug("Received proxy: %s", proxy)
    log.debug("Received urls: %s", urls)

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
                    [proxy, "Retry error. Proxy died while scanning.", True, datetime.now(timezone.utc)]
                )

        pool.close()
        pool.join()

    except Exception as my_exception:  # pylint: disable=broad-except
        # catch _anything_ that goes wrong, log it to the sentry/logfile
        # This is done to still return the scanproxy so it can be released.
        log.exception("Unexpected crash in qualys bulk scan: %s", my_exception)

    # return the proxy so it can be closed.
    # The scan results are created as separate tasks in the scan thread.
    return proxy


# keeps scanning in a loop until it has the data to fire a
def qualys_scan_thread(proxy: Dict[str, Any], url: str):
    normal_waiting_time = 30
    error_waiting_time = 60  # seconds until retry, can be increased when queues are full. Max = 180
    max_waiting_time = 360

    data = {}

    while True:
        try:
            api_result = service_provider_scan_via_api_with_limits(proxy, url)
            data = api_result["data"]
        except requests.RequestException:
            # ex: ('Connection aborted.', ConnectionResetError(54, 'Connection reset by peer'))
            # ex: EOF occurred in violation of protocol (_ssl.c:749)
            log.exception("(Network or Server) Error when contacting Qualys for scan on %s.", url)
            sleep(60)
            # continue

        # Store debug data in database (this task has no direct DB access due to scanners queue).
        # Not needed anymore, works as nintended.
        # scratch.apply_async([url, data])
        # Always log to console. Don't ask the database (constance) if this should happen.
        report_to_console(url, data)

        # Qualys is already running a scan on this url
        if "status" in data:
            # Qualys has completed the scan of the url and has a result.
            if data["status"] in ["READY", "ERROR"]:
                # scan completed
                # store the result on the storage queue.
                log.debug("Qualys scan finished on %s.", url)
                process_qualys_result.apply_async([data, url])
                return True

            log.debug(
                "Scan on %s has not yet finished. Waiting %s seconds before next update.", url, normal_waiting_time
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
                log.info("Error occurred while scanning %s: qualys is at full capacity, trying later.", url)
                sleep(error_waiting_time)
                # Don't break out of the loop...
                # continue

            # We're going too fast with new assessments. Back off.
            if error_message.startswith("Concurrent assessment limit reached"):
                log.error(
                    "Too many concurrent assessments: Are you running multiple scans from the same IP? "
                    "Concurrent scans slowly lower the concurrency limit of 25 concurrent scans to zero. "
                    "Slow down. %s",
                    data["errors"][0]["message"],
                )
                if error_waiting_time < max_waiting_time:
                    error_waiting_time += 60
                    sleep(error_waiting_time)
                    # continue

            if error_message.startswith("Too many concurrent assessments"):
                log.info("Error occurred while scanning %s: Too many concurrent assessments.", url)
                if error_waiting_time < max_waiting_time:
                    error_waiting_time += 60
                    sleep(error_waiting_time)
                    # continue

            # All other situations that we did not foresee...
            log.error("Unexpected error from API on %s: %s", url, str(data))

        # This is an undefined state.
        # scan started without errors. It's probably pending. Reset the waiting time to 60 seconds again as we
        # we want to get the result asap.
        log.debug("Got to an undefined state on qualys scan on %s. Scan has not finished, and we're retrying.", url)
        sleep(error_waiting_time)


@app.task(queue="storage", ignore_result=True)
def process_qualys_result(data, url: str):
    """Receive the JSON response from Qualys API, processes this result and stores it in database."""

    # log.info(data)
    # log.info(dir(data))

    # a normal completed scan.
    if data["status"] == "READY" and "endpoints" in data.keys():
        save_scan(url, data)
        return

    # missing endpoints: url propably resolves but has no TLS?
    if data["status"] == "READY":
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


def report_to_console(domain: str, data: Dict[str, Any]):
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
            log.debug("%s (IP: %s) = %s", domain, endpoint["ipAddress"], endpoint.get("grade", "No TLS"))

    if status in ["DNS", "ERROR"]:
        log.debug("%s %s: Got message: %s", domain, data["status"], data.get("statusMessage", "unknown"))

    if data["status"] == "IN_PROGRESS":
        for endpoint in data["endpoints"]:
            log.debug("%s, ep: %s. status: %s", domain, endpoint["ipAddress"], endpoint.get("statusMessage", "0"))

    if status == "unknown":
        log.error("Unexpected data received for domain: %s, %s", domain, data)


# Qualys is a service that is constantly attacked / ddossed and very unreliable. So try a couple of times before
# giving up. It can even be down for half a day. Waiting a little between retries.
@retry(wait=wait_fixed(30), before=before_log(log, logging.DEBUG))
def service_provider_scan_via_api_with_limits(proxy: Dict[str, Any], domain: str):
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
        proxies={proxy["protocol"]: proxy["address"]},
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


def save_scan(url: str, data: Any):
    """
    When a scan is ready it can contain both ipv4 and ipv6 endpoints. Sometimes multiple of both.
    It stores _one_ result for v4 and one for v6. It might be that one of the v6 is off, it stores the first one.
    # todo: store the worst one.

    :param url:
    :param data: raw JSON data from qualys
    :return:
    """

    log.debug("Saving scan for %s", url)

    # this scanner only does https/443, so there are two possible entry points for a domain:
    stored_ipv6 = False
    stored_ipv4 = False

    log.debug("Found %s endpoints in data.", len(data["endpoints"]))

    # should be unique(!)
    db_url = Url.objects.all().filter(url=url).last()
    if not db_url:
        return

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
        log.debug("Message for endpoint %s is %s.", qualys_endpoint["ipAddress"], message)

        # Qualys might discover endpoints we don't have yet. In that case, be pragmatic and create the endpoint.
        failmap_endpoint = force_get_endpoint(
            protocol="https", url_id=db_url.id, port=443, ip_version=ip_version, origin="tls_qualys"
        )

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
            store_endpoint_scan_result("tls_qualys_certificate_trusted", failmap_endpoint.pk, "scan_error", message)
            store_endpoint_scan_result("tls_qualys_encryption_quality", failmap_endpoint.pk, "scan_error", message)
            continue

        if message not in ["Ready"]:
            continue

        rating = qualys_endpoint["grade"]
        rating_no_trust = qualys_endpoint["gradeTrustIgnored"]

        trust = "not trusted" if rating == "T" else "trusted"
        store_endpoint_scan_result(
            "tls_qualys_certificate_trusted",
            failmap_endpoint.pk,
            trust,
            "",
            evidence=json.dumps(get_certs(data, ip_version)),
        )
        store_endpoint_scan_result("tls_qualys_encryption_quality", failmap_endpoint.pk, rating_no_trust, "")

    return


def get_certs(scan_data, ip_version: int) -> List[Dict[str, Any]]:
    # get all certificate data from qualys measurements
    cert_hashes = set()

    relevant_certs = []

    # filter the certs that fit the ip-version
    for qualys_endpoint in scan_data["endpoints"]:
        if ":" in qualys_endpoint["ipAddress"] and ip_version == 6:
            relevant_certs.append(qualys_endpoint.get("details", {}).get("cert", {}))

        if "." in qualys_endpoint["ipAddress"] and ip_version == 4:
            relevant_certs.append(qualys_endpoint.get("details", {}).get("cert", {}))

    # filter out duplicate certificates
    unique_certs = []
    for cert in relevant_certs:
        if "sha1Hash" not in cert:
            continue

        if cert["sha1Hash"] not in cert_hashes:
            cert_hashes.add(cert["sha1Hash"])
            unique_certs.append(cert)

    return unique_certs


@app.task(queue="storage", ignore_result=True)
def scratch(domain, data):
    log.debug("Scratching data for %s", domain)
    scratchpad = TlsQualysScratchpad()
    scratchpad.domain = domain
    scratchpad.data = json.dumps(data)
    scratchpad.save()
