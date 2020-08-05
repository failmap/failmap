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
import random
from datetime import datetime, timedelta
from http.client import BadStatusLine
from multiprocessing.pool import ThreadPool
from time import sleep
from typing import List

import pytz
import requests
from celery import Task, group
from constance import config
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from requests.exceptions import ConnectTimeout, ProxyError, SSLError
from tenacity import RetryError, before_log, retry, stop_after_attempt, wait_fixed
from urllib3.exceptions import ProtocolError

from websecmap.celery import app
from websecmap.organizations.models import Url, Organization
from websecmap.scanners.models import Endpoint, ScanProxy, TlsQualysScratchpad
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.__init__ import allowed_to_scan, q_configurations_to_scan, chunks2
from websecmap.scanners.scanner.http import store_url_ips
from websecmap.scanners import plannedscan

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


def plan_scan(urls_filter: dict = dict(), **kwargs):

    if not allowed_to_scan("tls_qualys"):
        return None

    # This is a query for the TLS scanner that only scans endpoints that did not have a scan yet.
    # Plan scans for endpoints that never have been scanned:
    urls = Url.objects.filter(
        q_configurations_to_scan(),
        is_dead=False,
        not_resolvable=False,
        endpoint__protocol="https",
        endpoint__port=443,
        endpoint__is_dead=False,
        **urls_filter
    ).annotate(
        nr_of_scans=Count('endpoint__endpointgenericscan')
    ).filter(
        nr_of_scans=0
    ).only('id', 'url')

    # Due to filtering on endpoints, the list of URLS is not distinct. We're making it so.
    plannedscan.request(activity="scan", scanner="tls_qualys", urls=list(set(urls)))

    # Scans for endpoints that have already been scanned:
    # Scan the bad ones more frequently than the good ones, to reduce the amount of requests.
    # todo: parameterize using settings in constance.
    parameter_sets = [
        {
            "exclude_urls_scanned_in_the_last_n_days": 7,
            "quality_levels": ["A", "A+", "A-", "trusted"]
        },
        {
            "exclude_urls_scanned_in_the_last_n_days": 3,
            "quality_levels": ["F", "C", "B", "not trusted"]
        }
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
            endpoint__endpointgenericscan__last_scan_moment__lte=timezone.now() - timedelta(
                days=parameter_set['exclude_urls_scanned_in_the_last_n_days']),
            endpoint__endpointgenericscan__rating__in=parameter_set['quality_levels'],
            **urls_filter
        ).only('id', 'url')
        print(urls.query)
        plannedscan.request(activity="scan", scanner="tls_qualys", urls=list(set(urls)))


def compose_manual_scan_task(organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    **kwargs):
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
        urls = Url.objects.filter(
            q_configurations_to_scan(),
            is_dead=False,
            not_resolvable=False,
            endpoint__protocol="https",
            endpoint__port=443,
            endpoint__is_dead=False,
            organization__in=organizations,  # when empty, no results...
            **urls_filter
        ).order_by(
            '-endpoint__endpointgenericscan__latest_scan_moment'
        ).only('id', 'url')
    else:
        # use order by to get a few of the most outdated results...
        urls = Url.objects.filter(
            q_configurations_to_scan(),
            is_dead=False,
            not_resolvable=False,
            endpoint__protocol="https",
            endpoint__port=443,
            endpoint__is_dead=False,
            **urls_filter
        ).order_by(
            '-endpoint__endpointgenericscan__latest_scan_moment'
        ).only('id', 'url')

    # Urls are ordered randomly.
    # Due to filtering on endpoints, the list of URLS is not distinct. We're making it so.
    urls = list(set(urls))
    random.shuffle(urls)

    if not urls:
        log.warning('Applied filters resulted in no urls, thus no tls qualys tasks!')
        return group()

    log.info('Creating qualys scan task for %s urls for %s organizations.', len(urls), len(organizations))

    return compose_scan_task(urls)


def compose_planned_scan_task(**kwargs) -> Task:

    if not allowed_to_scan("tls_qualys"):
        return group()

    # size for the proxies and such is 25 /each
    urls = plannedscan.pickup(activity="scan", scanner="tls_qualys", amount=kwargs.get('amount', 25))
    return compose_scan_task(urls)


def compose_scan_task(urls):

    if not urls:
        return group()

    chunks = list(chunks2(urls, 25))

    tasks = []
    for chunk in chunks:

        tasks.append(group(claim_proxy.s(chunk[0])
                     | qualys_scan_bulk.s(chunk)
                     | release_proxy.s(chunk[0])
                     | plannedscan.finish_multiple.si('scan', 'tls_qualys', chunk)))

    return group(tasks)


# Use the same rate limiting as qualys_scan_bulk, otherwise all proxies are claimed before scans are made.
# which would mean a lot of proxies could be claimed days in advance of the scan. That's not correct.
# this task floods and blocks the storage queue completely. The low prio seems to remedy this somewhat,
# as more important tasks are then handled as soon as one of these is finished.
# the storage queue should never be filled with this type of junk...
# removed rate limiting and such. If a proxy died it will stay claimed and it will fail the next verification
# the scan tasks will be added again and that's that.
# Moved this to a dedicated worker that can deadlock / block whatever it wants to block. We can add rate
# limiting again so not everything gets claimed in advance.
@app.task(queue='claim_proxy', rate_limit='30/h')
def claim_proxy(tracing_label=""):
    """ A proxy should first be claimed and then checked. If not, several scans might use the same proxy and thus
    crash. """

    # try to get the first available, fastest, proxy
    while True:

        log.debug(f"Attempting to claim a proxy to scan {tracing_label} et al...")

        try:

            with transaction.atomic():

                # proxies can die if they are limited too often.
                proxy = ScanProxy.objects.all().filter(
                    is_dead=False,
                    currently_used_in_tls_qualys_scan=False,
                    manually_disabled=False,
                    request_speed_in_ms__gte=1,
                    qualys_capacity_current=0
                ).order_by('request_speed_in_ms').first()

                if proxy:

                    # first claim to prevent duplicate claims
                    log.debug(f"Proxy {proxy.id} claimed for {tracing_label} et al...")
                    proxy.currently_used_in_tls_qualys_scan = True
                    proxy.last_claim_at = datetime.now(pytz.utc)
                    proxy.save(update_fields=['currently_used_in_tls_qualys_scan', 'last_claim_at'])

                    # we can't check for proxy quality here, as that will fill up the strorage with long tasks.
                    # instead run the proxy checking worker every hour or so to make sure the list stays fresh.
                    # if check_proxy(proxy):
                    #    log.debug('Using proxy %s for scan.' % proxy)
                    return proxy
                    # else:
                    #     log.debug('Proxy %s was not suitable for scanning. Trying another one in 60 seconds.' % proxy)

                else:
                    # do not log an error here, when forgetting to add proxies or if there are no clean proxies anymore,
                    # the queue might fill up with too many claim_proxy tasks. Each of them continuing in their own
                    # thread
                    # to get a proxy every 2 minutes (30/h). This can lead up to 30.000 issues per day.
                    # When you have over 500 proxy requests, things are off. It's better to start with a clean
                    # slate then.
                    log.debug(f'No proxies available for {tracing_label} et al. '
                              f'You can add more proxies to solve this. Will try again in 60 seconds.')

        except BaseException as e:
            # In some rare cases this method crashes, while it should be as reliable as can be.
            log.error(f"Exception occurred when requesting a proxy for {tracing_label} et al")
            log.exception(e)
            raise e

        sleep(60)


@app.task(queue='storage')
def release_proxy(proxy: ScanProxy, tracing_label=""):
    """As the claim proxy queue is ALWAYS filled, you cannot insert release proxy commands there..."""
    log.debug(f"Releasing proxy {proxy.id} claimed for {tracing_label} et al...")
    proxy.currently_used_in_tls_qualys_scan = False
    proxy.save(update_fields=['currently_used_in_tls_qualys_scan'])


@app.task(queue='internet')
def check_proxy(proxy: ScanProxy):
    # todo: service_provider_status should stop after a certain amount of requests.
    # Note that you MUST USE HTTPS proxies for HTTPS traffic! Otherwise your normal IP is used.

    log.debug(f"Testing proxy {proxy.id}")

    if not config.SCAN_PROXY_TESTING_URL:
        proxy_testing_url = "https://google.com/"
        log.debug("No SCAN_PROXY_TESTING_URL configured, falling back to google.com.")
    else:
        proxy_testing_url = config.SCAN_PROXY_TESTING_URL

    log.debug(f"Attempting to connect to testing url: {proxy_testing_url}")
    # send requests to a known domain to inspect the headers the proxies attach. There has to be something
    # that links various scans to each other.
    try:
        requests.get(
            proxy_testing_url,
            proxies={proxy.protocol: proxy.address},
            timeout=(API_NETWORK_TIMEOUT, API_SERVER_TIMEOUT),
            headers={
                'User-Agent': f"Request through proxy {proxy.id}",
                'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                'Accept-Language': 'en-US,en;q=0.5',
                'DNT': '1',
            }
        )

    # Storage is handled async, because you might not be on the machine that is able to save data.
    except ProxyError:
        log.debug("ProxyError, Perhaps because: proxy does not support https.")
        store_check_result.apply_async([proxy, "ProxyError, Perhaps because: proxy does not support https.", True,
                                        datetime.now(pytz.utc)])
        return False
    except SSLError:
        log.debug("SSL error received.")
        store_check_result.apply_async([proxy, "SSL error received.", True, datetime.now(pytz.utc)])
        return False
    except ConnectTimeout:
        log.debug("Connection timeout.")
        store_check_result.apply_async([proxy, "Connection timeout.", True, datetime.now(pytz.utc)])
        return False
    except ConnectionError:
        log.debug("Connection error.")
        store_check_result.apply_async([proxy, "Connection error.", True, datetime.now(pytz.utc)])
        return False
    except ProtocolError:
        log.debug("Protocol error.")
        store_check_result.apply_async([proxy, "Protocol error.", True, datetime.now(pytz.utc)])
        return False
    except BadStatusLine:
        log.debug("Bad status line.")
        store_check_result.apply_async([proxy, "Bad status line.", True, datetime.now(pytz.utc)])
        return False

    log.debug(f"Could connect to test site {proxy_testing_url}. Proxy is functional.")

    log.debug(f"Attempting to connect to the Qualys API.")
    try:
        api_results = service_provider_status(proxy)
    except RetryError:
        log.debug("Retry error. Could not connect.")
        store_check_result.apply_async([proxy, "Retry error. Could not connect.", True, datetime.now(pytz.utc)])
        return False

    # tried a few times, no result. Proxy is dead.
    if not api_results:
        log.debug("No result, proxy not reachable?")
        store_check_result.apply_async([proxy, "No result, proxy not reachable?", True, datetime.now(pytz.utc)])
        return False

    if api_results['max'] < 20 or api_results['this-client-max'] < 20 or api_results['current'] > 19:
        log.debug("Out of capacity %s." % proxy)
        store_check_result.apply_async([proxy, "Out of capacity.", True, datetime.now(pytz.utc),
                                        api_results['current'], api_results['max'], api_results['this-client-max']])
        return False
    else:
        # todo: Request time via the proxy. Just getting google.com might take a lot of time...
        try:
            speed = requests.get('https://apple.com',
                                 proxies={proxy.protocol: proxy.address},
                                 timeout=(API_NETWORK_TIMEOUT, API_SERVER_TIMEOUT)
                                 ).elapsed.total_seconds()
            log.debug("Website retrieved.")
        except ProxyError:
            log.debug("Could not retrieve website.")
            store_check_result.apply_async([proxy, "Could not retrieve website.", True, datetime.now(pytz.utc),
                                            api_results['current'], api_results['max'], api_results['this-client-max']])
            return False
        except ConnectTimeout:
            log.debug("Proxy too slow for standard site.")
            store_check_result.apply_async([proxy, "Proxy too slow for standard site.", True, datetime.now(pytz.utc),
                                            api_results['current'], api_results['max'], api_results['this-client-max']])
            return False

        # todo: how to check the headers the proxy sends to the client? That requires a server to receive
        # requests. Proxies wont work if they are not "elite", aka: not revealing the internet user behind them.
        # otherwise the data will be coupled to a single client.

        log.debug(f"Proxy accessible. Capacity available. {proxy.id}.")
        store_check_result.apply_async([proxy, "Proxy accessible. Capacity available.", False, datetime.now(pytz.utc),
                                        api_results['current'], api_results['max'], api_results['this-client-max'],
                                        int(speed * 1000)])
        return True


@app.task(queue="storage")
def store_check_result(proxy: ScanProxy, check_result, is_dead: bool, check_result_date,
                       qualys_capacity_current=-1, qualys_capacity_max=-1,
                       qualys_capacity_this_client=-1, request_speed_in_ms=-1):
    """Separates this to storage, so that capacity scans can be performed on another worker."""

    proxy.is_dead = is_dead
    proxy.check_result = check_result
    proxy.check_result_date = check_result_date
    proxy.qualys_capacity_max = qualys_capacity_max
    proxy.qualys_capacity_current = qualys_capacity_current
    proxy.qualys_capacity_this_client = qualys_capacity_this_client
    proxy.request_speed_in_ms = request_speed_in_ms
    proxy.save()


# It's possible a lot of scans start at the same time. In that case the API does not have a notion of how many scans
# are running (this takes a while). This results in too many requests and still a lot of errors. To avoid that this
# method has been rate limited to one per minute per worker. This gives a bit of slack.

# Note that this is a per worker instance rate limit, and not a global rate limit.
# http://docs.celeryproject.org/en/latest/userguide/tasks.html

# scan takes about 30 minutes.
# 12 / hour = 1 every 5 minutes. In 30 minutes 6 scans will run at the same time. We used to have 10.
# 20 / hour = 1 every 3 minutes. In 30 minutes 10 scans will run at the same time.
# 30 / hours = 1 every 2 minutes. In 30 minutes 15 scans will run at the same time.
@app.task(queue='qualys', rate_limit='30/h', acks_late=True)
def qualys_scan_bulk(proxy: ScanProxy, urls: List[Url]):

    log.debug('Initiating bulk scan')
    log.debug('Received proxy: %s' % proxy)
    log.debug('Received urls: %s' % urls)

    # Using this all scans stay on the same server (so no ip-hopping between scans, which limits the available
    # capacity severely.
    # Using this solution still uses parallel scans, while not having to rely on the black-box of redis and celery
    # that have caused priority shifts. This is much faster and easier to understand.

    # start one every 60 seconds, a thread can manage itself if too many are running.
    pool = ThreadPool(25)

    # Even if qualys is down, it will just wait until it knows you can add more... And the retry is infinite
    # every 30 seconds. So they may be even down for a day and it will continue.
    for url in urls:

        try:
            api_results = service_provider_status(proxy)
            while api_results['max'] < 20 or api_results['this-client-max'] < 20 or api_results['current'] > 19:
                log.debug("Running out of capacity, waiting to start new scan.")
                sleep(70)
                api_results = service_provider_status(proxy)

            pool.apply_async(qualys_scan_thread, [proxy, url])
            sleep(70)

        except RetryError:
            log.debug("Retry error. Could not connect to proxy anymore.")
            store_check_result.apply_async([proxy, "Retry error. Proxy died while scanning.", True,
                                            datetime.now(pytz.utc)])

    pool.close()
    pool.join()

    # return the proxy so it can be closed.
    # The scan results are created as separate tasks in the scan thread.
    return proxy


# keeps scanning in a loop until it has the data to fire a
def qualys_scan_thread(proxy, url):

    waiting_time = 60  # seconds until retry, can be increased when queues are full. Max = 180
    max_waiting_time = 360

    data = {}

    while True:
        try:
            api_result = service_provider_scan_via_api_with_limits(proxy, url.url)
            data = api_result['data']
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
        if 'status' in data:
            # Qualys has completed the scan of the url and has a result.
            if data['status'] in ["READY", "ERROR"]:
                # scan completed
                # store the result on the storage queue.
                log.debug(f"Qualys scan finished on {url.url}.")
                process_qualys_result.apply_async([data, url])
                return True
            else:
                log.debug(f"Scan on {url.url} has not yet finished. Waiting {waiting_time} seconds before next update.")
                sleep(waiting_time)
                # Don't break out of the loop...
                # continue

        # The API is in error state, let's see if we can be nice and recover.
        if "errors" in data:
            error_message = data['errors'][0]['message']
            # {'errors': [{'message': 'Running at full capacity. Please try again later.'}], 'status': 'FAILURE'}
            # Don't increase the amount of waiting time yet... try again in a minute.
            if error_message == "Running at full capacity. Please try again later.":
                # this happens all the time, so don't raise an exception but just make a log message.
                log.info(f"Error occurred while scanning {url.url}: qualys is at full capacity, trying later.")
                sleep(waiting_time)
                # Don't break out of the loop...
                # continue

            # We're going too fast with new assessments. Back off.
            if error_message.startswith("Concurrent assessment limit reached"):
                log.error(f"Too many concurrent assessments: Are you running multiple scans from the same IP? "
                          f"Concurrent scans slowly lower the concurrency limit of 25 concurrent scans to zero. "
                          f"Slow down. {data['errors'][0]['message']}")
                if waiting_time < max_waiting_time:
                    waiting_time += 60
                    sleep(waiting_time)
                    # continue

            if error_message.startswith("Too many concurrent assessments"):
                log.info(f"Error occurred while scanning {url.url}: Too many concurrent assessments.")
                if waiting_time < max_waiting_time:
                    waiting_time += 60
                    sleep(waiting_time)
                    # continue

            # All other situations that we did not foresee...
            log.error("Unexpected error from API on %s: %s", url.url, str(data))

        # This is an undefined state.
        # scan started without errors. It's probably pending. Reset the waiting time to 60 seconds again as we
        # we want to get the result asap.
        waiting_time = 60
        log.debug(f"Got to an undefined state on qualys scan on {url.url}. Scan has not finished, and we're retrying.")
        sleep(waiting_time)


@app.task(queue='storage')
def process_qualys_result(data, url):
    """Receive the JSON response from Qualys API, processes this result and stores it in database."""

    # log.info(data)
    # log.info(dir(data))

    # a normal completed scan.
    if data['status'] == "READY" and 'endpoints' in data.keys():
        save_scan(url, data)
        return

    # missing endpoints: url propably resolves but has no TLS?
    elif data['status'] == "READY":
        scratch(url, data)
        raise ValueError("Found no endpoints in ready scan. Todo: How to handle this?")

    # Not resolving
    if data['status'] == "ERROR":
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

    status = data.get('status', 'unknown')

    if status == "READY":
        for endpoint in data['endpoints']:
            log.debug("%s (IP: %s) = %s" % (domain, endpoint['ipAddress'], endpoint.get('grade', 'No TLS')))

    if status in ['DNS', 'ERROR']:
        log.debug("%s %s: Got message: %s", domain, data['status'], data.get('statusMessage', 'unknown'))

    if data['status'] == "IN_PROGRESS":
        for endpoint in data['endpoints']:
            log.debug("%s, ep: %s. status: %s" % (domain, endpoint['ipAddress'], endpoint.get('statusMessage', '0')))

    if status == 'unknown':
        log.error("Unexpected data received for domain: %s, %s" % (domain, data))


# Qualys is a service that is constantly attacked / ddossed and very unreliable. So try a couple of times before
# giving up. It can even be down for half a day. Waiting a little between retries.
@retry(wait=wait_fixed(30), before=before_log(log, logging.INFO))
def service_provider_scan_via_api_with_limits(proxy, domain):
    # API Docs: https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md
    payload = {
        'host': domain,  # host that will be scanned for tls
        'publish': "off",  # will not be published on the front page of the ssllabs site
        'startNew': "off",  # that's done automatically when needed by service provider
        'fromCache': "off",  # cache can have mismatches, but is ignored when startnew. We prefer cache as the cache on
        # qualys is not long lived. We prefer it because it might give back a result faster.
        'ignoreMismatch': "on",  # continue a scan, even if the certificate is for another domain
        'all': "done"  # ?
    }

    response = requests.get(
        "https://api.ssllabs.com/api/v2/analyze",
        params=payload,
        timeout=(API_NETWORK_TIMEOUT, API_SERVER_TIMEOUT),  # 30 seconds network, 30 seconds server.
        headers={
            'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/601.3.9 "
                          "(KHTML, like Gecko) Version/9.0.2 Safari/601.3.9",
            'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            'Accept-Language': 'en-US,en;q=0.5',
            'DNT': '1',
        },
        proxies={proxy.protocol: proxy.address},
        cookies={}
    )

    # log.debug(vars(response))  # extreme debugging
    log.debug("Assessments: max: %s, current: %s, this client: %s, this: %s, proxy: %s",
              response.headers.get('X-Max-Assessments', 25),
              response.headers.get('X-Current-Assessments', 0),
              response.headers.get('X-ClientMaxAssessments', 25),
              domain,
              proxy
              )

    return {'max': int(response.headers.get('X-Max-Assessments', 25)),
            'current': int(response.headers.get('X-Current-Assessments', 0)),
            'this-client-max': int(response.headers.get('X-ClientMaxAssessments', 25)),
            'data': response.json()}


@retry(wait=wait_fixed(30), stop=stop_after_attempt(3), before=before_log(log, logging.INFO))
def service_provider_status(proxy):
    # API Docs: https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md

    response = requests.get(
        "https://api.ssllabs.com/api/v2/getStatusCodes",
        params={},
        timeout=(API_NETWORK_TIMEOUT, API_SERVER_TIMEOUT),  # 30 seconds network, 30 seconds server.
        headers={
            'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_1) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/79.0.3945.130 Safari/537.36",
            'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,"
                      "*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            'Accept-Language': 'en-US,en;q=0.5',
            'DNT': '1',
        },
        proxies={proxy.protocol: proxy.address},
        cookies={}
    )

    # inspect to see if there are cookies or other tracking variables.
    log.debug("Cookies: %s Proxy: %s" % (proxy, response.cookies))

    """
    Always the same response. This is just used to get a correct response and the available capacity.

     {'statusDetails': {'TESTING_PROTOCOL_INTOLERANCE_399': 'Testing Protocol Intolerance (TLS 1.152)',
     'PREPARING_REPORT': 'Preparing the report', 'TESTING_SESSION_RESUMPTION': 'Testing session resumption',
     'RETRIEVING_CERT_V3__NO_SNI': 'Retrieving certificate', 'TESTING_NPN': 'Testing NPN',
     'RETRIEVING_CERT_V3__SNI_APEX': 'Retrieving certificate', 'TESTING_CVE_2014_0224': 'Testing CVE-2014-0224',
     'TESTING_CAPABILITIES': 'Determining server capabilities', 'TESTING_CVE_2016_2107': 'Testing CVE-2016-2107',
     'TESTING_HEARTBLEED': 'Testing Heartbleed', 'TESTING_PROTO_3_3_V2H': 'Testing TLS 1.1 (v2 handshake)',
     'TESTING_SESSION_TICKETS': 'Testing Session Ticket support', 'VALIDATING_TRUST_PATHS': 'Validating trust paths',
     'TESTING_RENEGOTIATION': 'Testing renegotiation', 'TESTING_HTTPS': 'Sending one complete HTTPS request',
     'TESTING_ALPN': 'Determining supported ALPN protocols', 'TESTING_V2H_HANDSHAKE': 'Testing v2 handshake',
     'TESTING_STRICT_RI': 'Testing Strict Renegotiation', 'TESTING_HANDSHAKE_SIMULATION': 'Simulating handshakes',
     'TESTING_SUITES_DEPRECATED': 'Testing deprecated cipher suites', 'TESTING_STRICT_SNI': 'Testing Strict SNI',
     'TESTING_PROTOCOL_INTOLERANCE_499': 'Testing Protocol Intolerance (TLS 2.152)', 'TESTING_PROTO_3_1_V2H':
     'Testing TLS 1.0 (v2 handshake)', 'TESTING_TLS_VERSION_INTOLERANCE': 'Testing TLS version intolerance',
     'TESTING_BLEICHENBACHER': 'Testing Bleichenbacher', 'TESTING_PROTOCOL_INTOLERANCE_304':
     'Testing Protocol Intolerance (TLS 1.3)', 'TESTING_SUITES_BULK': 'Bulk-testing less common cipher suites',
     'TESTING_BEAST': 'Testing for BEAST', 'TESTING_PROTO_2_0': 'Testing SSL 2.0', 'TESTING_TICKETBLEED':
     'Testing Ticketbleed', 'BUILDING_TRUST_PATHS': 'Building trust paths', 'TESTING_PROTO_3_1': 'Testing TLS 1.0',
     'TESTING_PROTO_3_0_V2H': 'Testing SSL 3.0 (v2 handshake)', 'TESTING_PROTO_3_0': 'Testing SSL 3.0',
     'TESTING_PROTOCOL_INTOLERANCE_300': 'Testing Protocol Intolerance (SSL 3.0)', 'TESTING_PROTOCOL_INTOLERANCE_301':
     'Testing Protocol Intolerance (TLS 1.0)', 'TESTING_PROTOCOL_INTOLERANCE_302':
     'Testing Protocol Intolerance (TLS 1.1)', 'TESTING_SUITES_NO_SNI': 'Observed extra suites during simulation,
     Testing cipher suites without SNI support', 'TESTING_EC_NAMED_CURVES': 'Determining supported named groups',
     'TESTING_PROTOCOL_INTOLERANCE_303': 'Testing Protocol Intolerance (TLS 1.2)', 'TESTING_OCSP_STAPLING_PRIME':
     'Trying to prime OCSP stapling', 'TESTING_DROWN': 'Testing for DROWN', 'TESTING_EXTENSION_INTOLERANCE':
     'Testing Extension Intolerance (might take a while)', 'TESTING_OCSP_STAPLING': 'Testing OCSP stapling',
     'TESTING_SSL2_SUITES': 'Checking if SSL 2.0 has any ciphers enabled', 'TESTING_SUITES':
     'Determining available cipher suites', 'TESTING_ECDHE_PARAMETER_REUSE': 'Testing ECDHE parameter reuse',
     'TESTING_PROTO_3_2_V2H': 'Testing TLS 1.1 (v2 handshake)', 'TESTING_POODLE_TLS': 'Testing POODLE against TLS',
     'RETRIEVING_CERT_TLS13': 'Retrieving certificate', 'RETRIEVING_CERT_V3__SNI_WWW': 'Retrieving certificate',
     'TESTING_PROTO_3_4': 'Testing TLS 1.3', 'TESTING_COMPRESSION': 'Testing compression', 'CHECKING_REVOCATION':
     'Checking for revoked certificates', 'TESTING_SUITE_PREFERENCE': 'Determining cipher suite preference',
     'TESTING_PROTO_3_2': 'Testing TLS 1.1', 'TESTING_PROTO_3_3': 'Testing TLS 1.2', 'TESTING_LONG_HANDSHAKE':
     'Testing Long Handshake (might take a while)'}}
    """

    # log.debug(vars(response))  # extreme debugging
    # The x-max-assements etc have been removed from the response headers in december 2019.
    # always return the max available. And make sure the claiming works as intended.
    log.debug("Status: max: %s, current: %s, this client: %s, proxy: %s",
              response.headers.get('X-Max-Assessments', 25),
              response.headers.get('X-Current-Assessments', 0),
              response.headers.get('X-ClientMaxAssessments', 25),
              proxy.id)

    return {'max': int(response.headers.get('X-Max-Assessments', 25)),
            'current': int(response.headers.get('X-Current-Assessments', 0)),
            'this-client-max': int(response.headers.get('X-ClientMaxAssessments', 25)),
            'data': response.json()}


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

    # Scan can contain multiple IPv4 and IPv6 endpoints, for example, four of each.
    for qualys_endpoint in data['endpoints']:
        """
        qep['grade']  # T, if trust issues.
        qep['gradeTrustIgnored']  # A+ to F
        """

        # Prevent storage of more than one result for either IPv4 and IPv6.
        if stored_ipv6 and ":" in qualys_endpoint['ipAddress']:
            continue

        if stored_ipv4 and ":" not in qualys_endpoint['ipAddress']:
            continue

        if ":" in qualys_endpoint['ipAddress']:
            stored_ipv6 = True
            ip_version = 6
        else:
            stored_ipv4 = True
            ip_version = 4
        # End prevent duplicates

        message = qualys_endpoint['statusMessage']

        if message in [
                "Unable to connect to the server",
                "Failed to communicate with the secure server",
                "Unexpected failure",
                "Failed to obtain certificate",
                "IP address is from private address space (RFC 1918)",
                "No secure protocols supported",
                "Certificate not valid for domain name"]:
            # Note: Certificate not valid for domain name can be ignored with correct API setting.
            # Nothing to store: something went wrong at the API side and we can't fix that.
            continue

        if message not in ["Ready"]:
            continue

        rating = qualys_endpoint['grade']
        rating_no_trust = qualys_endpoint['gradeTrustIgnored']

        # Qualys might discover endpoints we don't have yet. In that case, be pragmatic and create the endpoint.
        failmap_endpoint = Endpoint.force_get(url, ip_version, 'https', 443)

        if rating == "T":
            trust = "not trusted"
        else:
            trust = "trusted"

        store_endpoint_scan_result('tls_qualys_certificate_trusted', failmap_endpoint, trust, "")
        store_endpoint_scan_result('tls_qualys_encryption_quality', failmap_endpoint, rating_no_trust, "")

    # Store IP address of the scan as metadata
    ips = [ipaddress.ip_address(endpoint['ipAddress']).compressed for endpoint in data['endpoints']]
    store_url_ips(url, ips)
    return


@app.task(queue='storage')
def scratch(domain, data):
    log.debug("Scratching data for %s", domain)
    scratchpad = TlsQualysScratchpad()
    scratchpad.domain = domain
    scratchpad.data = json.dumps(data)
    scratchpad.save()
