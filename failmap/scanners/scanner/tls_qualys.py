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

import pytz
import requests
from celery import Task, group, states
from django.conf import settings

from failmap.celery import PRIO_HIGH, PRIO_NORMAL, app
from failmap.organizations.models import Organization, Url
from failmap.scanners.models import Endpoint, TlsQualysScratchpad
from failmap.scanners.scanmanager.tlsqualys_scan_manager import TlsQualysScanManager
from failmap.scanners.scanner.http import store_url_ips
from failmap.scanners.scanner.scanner import allowed_to_scan, q_configurations_to_scan

API_NETWORK_TIMEOUT = 30
API_SERVER_TIMEOUT = 30

log = logging.getLogger(__name__)


@app.task(queue="storage")
def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:

    if not allowed_to_scan("scanner_tls_qualys"):
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
            organization__in=organizations,  # whem empty, no results...
            **urls_filter,
        ).exclude(endpoint__tlsqualysscan__last_scan_moment__gte=datetime.now(tz=pytz.utc) - timedelta(days=7)
                  ).order_by("?")
    else:
        urls = Url.objects.filter(
            q_configurations_to_scan(),
            is_dead=False,
            not_resolvable=False,
            endpoint__protocol="https",
            endpoint__port=443,
            endpoint__is_dead=False,
            **urls_filter,
        ).exclude(endpoint__tlsqualysscan__last_scan_moment__gte=datetime.now(tz=pytz.utc) - timedelta(days=7)
                  ).order_by("?")

    # Urls are ordered randomly.
    # Due to filtering on endpoints, the list of URLS is not distinct. We're making it so.
    urls = list(set(urls))

    if endpoints_filter:
        raise NotImplementedError('This scanner needs to be refactored to scan per endpoint.')

    if not urls:
        log.warning('Applied filters resulted in no urls, thus no tls qualys tasks!')
        return group()

    log.info('Creating qualys scan task for %s urls for %s organizations.',
             len(urls), len(organizations))

    # create tasks for scanning all selected urls as a single managable group
    task = group(qualys_scan.si(url) | process_qualys_result.s(url) for url in urls)

    return task


@app.task(
    # http://docs.celeryproject.org/en/latest/userguide/tasks.html#Task.rate_limit
    # start at most 1 qualys task per minute to not get our IP blocked

    # After starting a scan you can read it out as much as you want. The problem lies with rate limiting
    # of starting the task.

    # Celery will at most start 1 new qualys_scan per minute, the 'retry' at
    # the end of this task will turn it from a rate_limited into a scheduled
    # tasks which makes this work nicely with Qualys API restrictions.

    # after starting a scan (1/m) you can read out every 20 seconds.
    # You can do so in the 10 minutes. If you don't, it will start a new scan which affects your rate limit.

    bind=True,
    # this task should run on an internet connected, distributed worker
    # also because of rate limiting put in its own queue to prevent blocking other tasks
    queue='scanners.qualys',
    # start at most 1 new task per minute (per worker)

    # 7 march 2018, qualys has new rate limits due to service outage.
    # We used to do 1/m which was fine, but we're now doing 1 every 2 minutes.
    # perhaps 0.5/m doesn't work... should maybe be.
    rate_limit='30/h',
)
def qualys_scan(self, url):
    """Acquire JSON scan result data for given URL from Qualys.

    A scan usually takes about two minutes. It _can_ take much longer depending on the amount
    of ip's qualys is able to find. Having eight different IP's is not special for some cloud
    hosters.

    :param url: object representing an url
    :return:
    """

    state = self.AsyncResult(self.request.id).state
    if state in [states.PENDING, states.STARTED]:
        log.info("Started attempt to scan %s. State: %s " % (url, state))
    if state == states.RETRY:
        log.info("Scan on %s continued..." % url)

    # Query Qualys API for information about this URL.
    try:
        data = service_provider_scan_via_api(url.url)
    except requests.RequestException:
        # ex: ('Connection aborted.', ConnectionResetError(54, 'Connection reset by peer'))
        # ex: EOF occurred in violation of protocol (_ssl.c:749)
        log.exception("(Network or Server) Error when contacting Qualys for scan on %s", url.url)
        # Initial scan (with rate limiting) has not been received yet, so add to the qualys queue again.
        raise self.retry(countdown=60, priorty=PRIO_NORMAL, max_retries=100, queue='scanners.qualys')

    # Create task for storage worker to store debug data in database (this
    # task has no direct DB access due to scanners queue).
    scratch.apply_async([url, data])

    if settings.DEBUG:
        report_to_console(url.url, data)  # for more debugging

    # Qualys is running a scan...
    if 'status' in data:
        # Qualys has completed the scan of the url and has a result for us. Continue the chain.
        # Qualys has found an error while scanning. Continue the chain.
        if data['status'] in ["READY", "ERROR"]:
            return data

    # The API is in error state, let's see if we can recover...
    # This is on API level, and not the content of the API
    if "errors" in data:
        # {'errors': [{'message': 'Running at full capacity. Please try again later.'}], 'status': 'FAILURE'}
        if data['errors'][0]['message'] == "Running at full capacity. Please try again later.":
            log.info("Re-queued scan, qualys is at full capacity.")
            raise self.retry(countdown=60, priorty=PRIO_NORMAL, max_retries=100, queue='scanners.qualys')
        # We have no clue, but we certainly don't want this running on the normal queue.
        # The amount of retries has been lowered, as this is a situation we don't know yet, we don't have to
        # keep on making the same mistakes at the API.
        if data['errors'][0]['message'].startswith("Concurrent assessment limit reached "):
            log.info("Too many concurrent assessments: Are you running multiple scans from the same IP? "
                     "Concurrent scans slowly lower the concurrency limit of 25 concurrent scans to zero. Slow down. "
                     "%s" % data['errors'][0]['message'])
            raise self.retry(countdown=120, priorty=PRIO_NORMAL, max_retries=100, queue='scanners.qualys')
        else:
            log.exception("Unexpected error from API on %s: %s", url.url, str(data))
            # We don't have to keep on failing... lowering the amount of retries.
            raise self.retry(countdown=120, priorty=PRIO_NORMAL, max_retries=5, queue='scanners.qualys')

    """
    While the documentation says to check every 10 seconds, we'll do that between every
    20 to 25, simply because it matters very little when scans are ran parralel.
    https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md
    """
    log.info('Still waiting for Qualys result on %s. Retrying task in 180 seconds. Status: %s' %
             (url.url, data.get('status', "unknown")))
    # not tested yet: report_to_console(url.url, data)
    # 10 minutes of retries... (20s seconds * 30 = 10 minutes)
    # The 'retry' converts this task instance from a rate_limited into a
    # scheduled task, so retrying tasks won't interfere with new tasks to be
    # started
    # We use a different queue here as only initial requests count toward the rate limit set by Qualys.
    # Do note: this really needs to be picked up within the first five minutes of starting the scan. If you don't
    # a new scan is started on this url and you'll run into rate limiting problems.
    # the more often you try to get the status, on the more workers it will run (increasing concurrency)
    # so if we check after two minutes, there will be a lot less workers with increasing concurrency as the
    # scan will probably be finished by then.
    raise self.retry(countdown=180, priorty=PRIO_HIGH, max_retries=100, queue='scanners')


@app.task(queue='storage')
def process_qualys_result(data, url):
    """Receive the JSON response from Qualys API, processes this result and stores it in database."""

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


def service_provider_scan_via_api(domain):
    # API Docs: https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md
    payload = {
        'host': domain,  # host that will be scanned for tls
        'publish': "off",  # will not be published on the front page of the ssllabs site
        'startNew': "off",  # that's done automatically when needed by service provider
        'fromCache': "on",  # cache can have mismatches, but is ignored when startnew. We prefer cache as the cache on
        # qualys is not long lived. We prefer it because it might give back a result faster.
        'ignoreMismatch': "on",  # continue a scan, even if the certificate is for another domain
        'all': "done"  # ?
    }

    response = requests.get(
        "https://api.ssllabs.com/api/v2/analyze",
        params=payload,
        timeout=(API_NETWORK_TIMEOUT, API_SERVER_TIMEOUT),  # 30 seconds network, 30 seconds server.
        headers={'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/601.3.9 "
                               "(KHTML, like Gecko) Version/9.0.2 Safari/601.3.9", }
    )

    # log.debug(vars(response))  # extreme debugging
    log.info("Assessments: max: %s, current: %s, this client: %s, this: %s",
             response.headers['X-Max-Assessments'],
             response.headers['X-Current-Assessments'],
             response.headers['X-ClientMaxAssessments'],
             domain
             )

    return response.json()


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
        TlsQualysScanManager.add_scan(failmap_endpoint, rating, rating_no_trust, "Ready")

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
