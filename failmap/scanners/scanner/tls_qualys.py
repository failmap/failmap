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

import pytz
import requests
from celery import Task, group
from django.conf import settings
from tenacity import before_log, retry, wait_fixed

from failmap.celery import app
from failmap.organizations.models import Organization, Url
from failmap.scanners.models import Endpoint, TlsQualysScratchpad
from failmap.scanners.scanmanager.tlsqualys_scan_manager import TlsQualysScanManager
from failmap.scanners.scanner.http import store_url_ips
from failmap.scanners.scanner.scanner import allowed_to_scan, q_configurations_to_scan

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


@app.task(queue="storage")
def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:

    # for some reason declaring the chunks function outside of this function does not resolve. I mean... why?
    # https://chrisalbon.com/python/data_wrangling/break_list_into_chunks_of_equal_size/
    # Create a function called "chunks" with two arguments, l and n:
    def chunks(l, n):
        # For item i in a range that is a length of l,
        for i in range(0, len(l), n):
            # Create an index range for l of n items:
            yield l[i:i + n]

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

    log.info('Creating qualys scan task for %s urls for %s organizations.', len(urls), len(organizations))

    # Split the urls up in chunks:
    chunks = list(chunks(urls, 25))
    task = group(qualys_scan_bulk.s(chunk) for chunk in chunks)
    return task


@app.task(queue='scanners.qualys')
def qualys_scan_bulk(urls):
    # Using this all scans stay on the same server (so no ip-hopping between scans, which limits the available
    # capacity severely.
    # Using this solution still uses parallel scans, while not having to rely on the black-box of redis and celery
    # that have caused priority shifts. This is much faster and easier to understand.

    # start one every 60 seconds, a thread can manage itself if too many are running.
    pool = ThreadPool(25)

    # Even if qualys is down, it will just wait until it knows you can add more... And the retry is infinite
    # every 30 seconds. So they may be even down for a day and it will continue.
    for url in urls:
        api_results = service_provider_status()
        while api_results['max'] < 20 or api_results['this-client-max'] < 20 or api_results['current'] > 19:
            log.debug("Running out of capacity, waiting to start new scan.")
            sleep(70)
            api_results = service_provider_status()

        pool.apply_async(qualys_scan_thread, [url])
        sleep(70)

    pool.close()
    pool.join()

    return


# keeps scanning in a loop until it has the data to fire a
def qualys_scan_thread(url):

    scan_completed = False
    data = {}
    waiting_time = 60  # seconds until retry, can be increased when queues are full. Max = 180
    max_waiting_time = 180

    while not scan_completed:
        try:
            api_result = service_provider_scan_via_api_with_limits(url.url)
            data = api_result['data']
        except requests.RequestException:
            # ex: ('Connection aborted.', ConnectionResetError(54, 'Connection reset by peer'))
            # ex: EOF occurred in violation of protocol (_ssl.c:749)
            log.exception("(Network or Server) Error when contacting Qualys for scan on %s", url.url)

        # Store debug data in database (this task has no direct DB access due to scanners queue).
        scratch.apply_async([url, data])

        if settings.DEBUG:
            report_to_console(url.url, data)

        # Qualys is already running a scan on this url
        if 'status' in data:
            # Qualys has completed the scan of the url and has a result.
            if data['status'] in ["READY", "ERROR"]:
                scan_completed = True

        # The API is in error state, let's see if we can be nice and recover.
        if "errors" in data:
            # {'errors': [{'message': 'Running at full capacity. Please try again later.'}], 'status': 'FAILURE'}
            # Don't increase the amount of waiting time yet... try again in a minute.
            if data['errors'][0]['message'] == "Running at full capacity. Please try again later.":
                log.error("Qualys is at full capacity, trying later.")

            # We're going too fast with new assessments. Back off.
            if data['errors'][0]['message'].startswith("Concurrent assessment limit reached "):
                log.error("Too many concurrent assessments: Are you running multiple scans from the same IP? "
                          "Concurrent scans slowly lower the concurrency limit of 25 concurrent scans to zero. "
                          "Slow down. ""%s" % data['errors'][0]['message'])
                if waiting_time < max_waiting_time:
                    waiting_time += 30
            if data['errors'][0]['message'].startswith("Too many concurrent assessments"):
                if waiting_time < max_waiting_time:
                    waiting_time += 30
            if data['errors'][0]['message'].startswith("Concurrent assessment limit reached"):
                if waiting_time < max_waiting_time:
                    waiting_time += 30
            else:
                log.error("Unexpected error from API on %s: %s", url.url, str(data))

        elif data:
            # scan started without errors. It's probably pending. Reset the waiting time to 60 seconds again as we
            # we want to get the result asap.
            waiting_time = 60

        log.debug("Waiting %s seconds before next update." % waiting_time)
        if not scan_completed:
            sleep(waiting_time)

    # scan completed
    # store the result on the storage queue.
    process_qualys_result.apply_async([data, url])
    return True


@app.task(queue='storage')
def process_qualys_result(data, url):
    """Receive the JSON response from Qualys API, processes this result and stores it in database."""

    log.info(data)
    log.info(dir(data))

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
def service_provider_scan_via_api_with_limits(domain):
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

    return {'max': int(response.headers['X-Max-Assessments']),
            'current': int(response.headers['X-Current-Assessments']),
            'this-client-max': int(response.headers['X-ClientMaxAssessments']),
            'data': response.json()}


@retry(wait=wait_fixed(30), before=before_log(log, logging.INFO))
def service_provider_status():
    # API Docs: https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md
    response = requests.get(
        "https://api.ssllabs.com/api/v2/getStatusCodes",
        params={},
        timeout=(API_NETWORK_TIMEOUT, API_SERVER_TIMEOUT),  # 30 seconds network, 30 seconds server.
        headers={'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/601.3.9 "
                               "(KHTML, like Gecko) Version/9.0.2 Safari/601.3.9", }
    )

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
    # log.debug(response)

    # log.debug(vars(response))  # extreme debugging
    log.info("Status: max: %s, current: %s, this client: %s",
             response.headers['X-Max-Assessments'],
             response.headers['X-Current-Assessments'],
             response.headers['X-ClientMaxAssessments'])

    return {'max': int(response.headers['X-Max-Assessments']),
            'current': int(response.headers['X-Current-Assessments']),
            'this-client-max': int(response.headers['X-ClientMaxAssessments']),
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
