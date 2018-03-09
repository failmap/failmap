"""
Manages endpoints:
 Protocols: https
 Ports: 443
 IP's: any related to a domain on mentioned protocols and ports.

This scanner harvests ips during scanning.

This class will scan any domain it's asked to. It will rate limit on domains that have
recently been scanned to not flood qualys (and keep in good standing). A scan at qualys
takes about 1 to 10 minutes. This script will make sure requests are not done too quickly.

This class can scan domains in bulk. All endpoints related to these scans are set on pending
before the scan starts. The caller of this class has to manage what URL's are scanned, when,
especially when handling new domains without endpoints to set to pending problems may occur
(problems = multiple scanners trying to scan the same domain at the same time).

Scans and grading is done by Qualys: it's their view of the internet, which might differ
from yours.

API Documentation:
https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md

"""
import ipaddress
import json
import logging
from datetime import date, datetime, timedelta

import pytz
import requests
from celery import Task, group
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from failmap.organizations.models import Organization, Url
from failmap.scanners.models import (Endpoint, EndpointGenericScan, TlsQualysScan,
                                     TlsQualysScratchpad)
from failmap.scanners.scanner_http import store_url_ips

from ..celery import PRIO_HIGH, PRIO_NORMAL, app

API_NETWORK_TIMEOUT = 30
API_SERVER_TIMEOUT = 30

log = logging.getLogger(__name__)


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    """Compose taskset to scan specified endpoints.

    *This is an implementation of `compose_task`. For more documentation about this concept, arguments and concrete
    examples of usage refer to `compose_task` in `types.py`.*

    """

    # The dummy scanner is an example of a scanner that scans on an endpoint
    # level. Meaning to create tasks for scanning, this function needs to be
    # smart enough to translate (filtered) lists of organzations and urls into a
    # (filtered) lists of endpoints (or use a url filter directly). This list of
    # endpoints is then used to create a group of tasks which would perform the
    # scan.

    # apply filter to organizations (or if no filter, all organizations)
    organizations = Organization.objects.filter(**organizations_filter)

    # Discover Endpoints will figure out if there is https and if port 443 is open.
    # apply filter to urls in organizations (or if no filter, all urls)
    # do not scan the same url within 24 hours.
    # we assume all endpoints are scanned at the same time (this is what qualys does)

    # scan only once in seven days. an emergency fix to make sure everything is scanned.
    # todo: force re-scan, where days is < 7, with 5000 scanning takes a while and a lot still goes wrong.
    urls = Url.objects.filter(
        is_dead=False,
        not_resolvable=False,
        endpoint__protocol="https",
        endpoint__port=443,
        organization__in=organizations, **urls_filter,
    ).exclude(endpoint__tlsqualysscan__last_scan_moment__gte=datetime.now(tz=pytz.utc) - timedelta(days=7)
              ).order_by("?")  # used to be endpoint__tlsqualysscan__last_scan_moment

    # ordered randomly: i didn't get a distinct set of urls due to the inner join on endpoint. Would like to do
    # oldest first to make sure everything is scanned more recently. To remove the join.
    urls = list(set(urls))

    if endpoints_filter:
        raise NotImplementedError('This scanner needs to be refactored to scan per endpoint.')

    if not urls:
        raise Exception('Applied filters resulted in no tasks!')

    log.info('Creating scan task for %s urls for %s organizations.',
             len(urls), len(organizations))

    # create tasks for scanning all selected urls as a single managable group
    task = group(qualys_scan.s(url) | process_qualys_result.s(url) for url in urls)

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
    rate_limit='0.5/m',
)
def qualys_scan(self, url):
    """Acquire JSON scan result data for given URL from Qualys.

    A scan usually takes about two minutes. It _can_ take much longer depending on the amount
    of ip's qualys is able to find. Having eight different IP's is not special for some cloud
    hosters.

    :param url: object representing an url
    :return:
    """

    # Query Qualys API for information about this URL.
    try:
        data = service_provider_scan_via_api(url.url)
    except requests.RequestException as e:
        # ex: ('Connection aborted.', ConnectionResetError(54, 'Connection reset by peer'))
        # ex: EOF occurred in violation of protocol (_ssl.c:749)
        log.exception("(Network or Server) Error when contacting Qualys for scan on %s", url.url)
        # Initial scan (with rate limiting) has not been received yet, so add to the qualys queue again.
        raise self.retry(countdown=60, priorty=PRIO_NORMAL, max_retries=30, queue='scanners.qualys')

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
            raise self.retry(countdown=60, priorty=PRIO_NORMAL, max_retries=30, queue='scanners.qualys')
        # We have no clue, but we certainly don't want this running on the normal queue.
        # The amount of retries has been lowered, as this is a situation we don't know yet, we don't have to
        # keep on making the same mistakes at the API.
        if data['errors'][0]['message'].startswith("Concurrent assessment limit reached "):
            log.info("Too many concurrent assessments: Are you running multiple scans from the same IP? "
                     "Concurrent scans slowly lower the concurrency limit of 25 concurrent scans to zero. Slow down. "
                     "%s" % data['errors'][0]['message'])
            raise self.retry(countdown=120, priorty=PRIO_NORMAL, max_retries=30, queue='scanners.qualys')
        else:
            log.exception("Unexpected error from API on %s: %s", url.url, str(data))
            # We don't have to keep on failing... lowering the amount of retries.
            raise self.retry(countdown=60, priorty=PRIO_NORMAL, max_retries=5, queue='scanners.qualys')

    """
    While the documentation says to check every 10 seconds, we'll do that between every
    20 to 25, simply because it matters very little when scans are ran parralel.
    https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md
    """
    log.info('Still waiting for Qualys result. Retrying task in 20 seconds.')
    # 10 minutes of retries... (20s seconds * 30 = 10 minutes)
    # The 'retry' converts this task instance from a rate_limited into a
    # scheduled task, so retrying tasks won't interfere with new tasks to be
    # started
    # We use a different queue here as only initial requests count toward the rate limit set by Qualys.
    # Do note: this really needs to be picked up within the first five minutes of starting the scan. If you don't
    # a new scan is started on this url and you'll run into rate limiting problems.
    raise self.retry(countdown=30, priorty=PRIO_HIGH, max_retries=30, queue='scanners')


@app.task(queue='storage')
def process_qualys_result(data, url):
    """Receive the JSON response from Qualys API, processes this result and stores it in database."""

    # a normal completed scan.
    if data['status'] == "READY" and 'endpoints' in data.keys():
        result = save_scan(url, data)
        clean_endpoints(url, data['endpoints'])
        return '%s %s' % (url, result)

    # missing endpoints: url propably resolves but has no TLS?
    elif data['status'] == "READY":
        # no endpoints whut?
        log.error("Found no endpoints in ready scan. Todo: How to handle this?")
        scratch(url, data)

    # Not resolving
    if data['status'] == "ERROR":
        """
        Error is usually "unable to resolve domain". This should kill the endpoint(s).
        todo: actually check on this.
        """
        scratch(url, data)  # we always want to see what happened.
        clean_endpoints(url, [])
        return '%s error' % url


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
    if 'status' in data.keys():
        if data['status'] == "READY":
            for endpoint in data['endpoints']:
                if 'grade' in endpoint.keys():
                    log.debug("%s (%s) = %s" % (domain, endpoint['ipAddress'], endpoint['grade']))
                else:
                    log.debug("%s = No TLS (0)" % domain)
                    log.debug("Message: %s" % endpoint['statusMessage'])

        if data['status'] == "DNS" or data['status'] == "ERROR":
            if 'statusMessage' in data.keys():
                log.debug("%s: Got message: %s", data['status'], data['statusMessage'])
            else:
                log.debug("%s: Got message: %s", data['status'], data)

        if data['status'] == "IN_PROGRESS":
            for endpoint in data['endpoints']:
                if 'statusMessage' in endpoint.keys():
                    log.debug(
                        "Domain %s in progress. Endpoint: %s. Msgs: %s "
                        % (domain, endpoint['ipAddress'], endpoint['statusMessage']))
                else:
                    log.debug(
                        "Domain %s in progress. Endpoint: %s. "
                        % (domain, endpoint['ipAddress']))
    else:
        # no idea how to handle this, so dumping the data...
        # ex: {'errors': [{'message': 'Concurrent assessment limit reached (7/7)'}]}
        log.error("Unexpected data received for domain: %s" % domain)
        log.error(data)


def service_provider_scan_via_api(domain):
    # API Docs: https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md
    payload = {
        'host': domain,  # host that will be scanned for tls
        'publish': "off",  # will not be published on the front page of the ssllabs site
        'startNew': "off",  # that's done automatically when needed by service provider
        'fromCache': "off",  # cache can have mismatches, but is ignored when startnew
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
    log.debug("Running assessments: max: %s, current: %s, client: %s",
              response.headers['X-Max-Assessments'],
              response.headers['X-Current-Assessments'],
              response.headers['X-ClientMaxAssessments']
              )

    return response.json()


def extract_ips(url, data):
    """
    Store some metadata / IP addresses.
    :param url:
    :param data:
    :return:
    """

    ips = [ipaddress.ip_address(endpoint['ipAddress']).compressed for endpoint in data['endpoints']]
    store_url_ips(url, ips)


def save_scan(url, data):
    """
    When a scan is ready it can contain both ipv4 and ipv6 endpoints. Sometimes multiple of both.

    :param url:
    :param data: raw JSON data from qualys
    :return:
    """
    log.debug("Saving scan for %s", url.url)
    extract_ips(url, data)

    # manage endpoints
    # An endpoint of the same IP could already exist and be dead. Keep it dead.
    # An endpoint can be made dead by not appearing in this list (cleaning)
    # or when qualys says so.

    # this scanner only does https/443, so there are two possible entrypoints for a domain:
    stored_ipv6 = False
    stored_ipv4 = False

    # keep kind of result for every endpoint to return at end of task
    results = []

    for qep in data['endpoints']:
        """
        qep['grade']  # T, if trust issues.
        qep['gradeTrustIgnored']  # A+ to F
        """
        if stored_ipv6 and ":" in qep['ipAddress']:
            continue

        if stored_ipv4 and ":" not in qep['ipAddress']:
            continue

        if ":" in qep['ipAddress']:
            stored_ipv6 = True
            ip_version = 6
        else:
            stored_ipv4 = True
            ip_version = 4

        message = qep['statusMessage']

        rating = 0
        rating_no_trust = 0
        if message in [
                "Unable to connect to the server",
                "Failed to communicate with the secure server",
                "Unexpected failure",
                "Failed to obtain certificate",
                "IP address is from private address space (RFC 1918)"]:
            rating = 0
            rating_no_trust = 0
            failmap_endpoint = kill_alive_and_get_endpoint('https', url, 443, ip_version, message)

        if message in [
                "Ready",
                "Certificate not valid for domain name",
                "No secure protocols supported"]:
            rating = qep['grade']
            rating_no_trust = qep['gradeTrustIgnored']
            failmap_endpoint = get_create_or_merge_endpoint('https', url, 443, ip_version)

        # possibly update the most recent scan, to save on records in the database
        previous_scan = TlsQualysScan.objects.filter(endpoint=failmap_endpoint). \
            order_by('-last_scan_moment').first()

        # don't store "failures" as complete scans (with 0 scores).
        # storing failures increases the amount of "waste" data. Since so many things can be not resolvable etc.
        if rating:
            if previous_scan:
                if all([previous_scan.qualys_rating == rating,
                        previous_scan.qualys_rating_no_trust == rating_no_trust]):
                    log.info("Scan on %s did not alter the rating, updating scan date only." % failmap_endpoint)
                    previous_scan.last_scan_moment = datetime.now(pytz.utc)
                    previous_scan.scan_time = datetime.now(pytz.utc)
                    previous_scan.scan_date = datetime.now(pytz.utc)
                    previous_scan.qualys_message = message
                    previous_scan.save()
                    results.append('no-change')

                else:
                    log.info("Rating changed on %s, we're going to save the scan to retain history" % failmap_endpoint)
                    create_scan(failmap_endpoint, rating, rating_no_trust, message)
                    results.append('rating-changed')
            else:
                log.info("This endpoint on %s was never scanned, creating a new scan." % failmap_endpoint)
                create_scan(failmap_endpoint, rating, rating_no_trust, message)
                results.append('first-scan')

    return results


def create_scan(endpoint, rating, rating_no_trust, status_message):
    tls_scan = TlsQualysScan()
    tls_scan.endpoint = endpoint
    tls_scan.qualys_rating = rating
    tls_scan.qualys_rating_no_trust = rating_no_trust
    tls_scan.last_scan_moment = datetime.now(pytz.utc)
    tls_scan.scan_time = datetime.now(pytz.utc)
    tls_scan.scan_date = datetime.now(pytz.utc)
    tls_scan.rating_determined_on = datetime.now(pytz.utc)
    tls_scan.qualys_message = status_message
    tls_scan.save()


# todo: this has to be moved to a more generic place
def get_create_or_merge_endpoint(protocol, url, port, ip_version):
    endpoints = Endpoint.objects.all().filter(
        protocol=protocol,
        url=url,
        port=port,
        ip_version=ip_version,
        is_dead=False).order_by('-discovered_on')

    count = endpoints.count()
    # 1: update the endpoint with the current information
    # 0: make new endpoint, representing the current result
    # >1: merge all these endpoints into one, something or someone made a mistake
    if count == 1:
        return endpoints[0]

    if count == 0:
        log.debug("Creating a new endpoint.")

        failmap_endpoint = Endpoint()
        try:
            failmap_endpoint.url = Url.objects.filter(url=url).first()
        except ObjectDoesNotExist:
            failmap_endpoint.url = ""
        failmap_endpoint.domain = url.url  # Filled for legacy reasons.
        failmap_endpoint.port = port
        failmap_endpoint.protocol = protocol
        failmap_endpoint.ip_version = ip_version
        failmap_endpoint.is_dead = False
        failmap_endpoint.discovered_on = datetime.now(pytz.utc)
        failmap_endpoint.save()

        return failmap_endpoint

    if count > 1:
        log.debug("Multiple similar endpoints detected for %s" % url)
        log.debug("Merging similar endpoints to a single one.")

        failmap_endpoint = endpoints.first()  # save the first one
        # and discard the rest
        for endpoint in endpoints:
            if endpoint == failmap_endpoint:
                continue

            # in the future there might be other scans too... be warned
            TlsQualysScan.objects.all().filter(endpoint=endpoint).update(endpoint=failmap_endpoint)
            EndpointGenericScan.objects.all().filter(endpoint=endpoint).update(endpoint=failmap_endpoint)
            endpoint.delete()

        return failmap_endpoint


def kill_endpoint(endpoint, message):
    endpoint.is_dead = True
    endpoint.is_dead_since = datetime.now(pytz.utc)
    endpoint.is_dead_reason = message
    endpoint.save()


def kill_alive_and_get_endpoint(protocol, url, port, ip_version, message):
    log.debug("Handing could not connect to server")

    endpoints = Endpoint.objects.all().filter(
        url=url,
        ip_version=ip_version,
        port=port,
        protocol=protocol,
        is_dead=False).order_by('-discovered_on')

    for ep in endpoints:
        kill_endpoint(ep, message)

    count = endpoints.count()
    # 1 or >1: save this scan to the latest endpoint that was known to be alive.
    # 0: Try to place the scan to the last dead endpoint. If there is nothing, create an endpoint.

    if count >= 1:
        log.debug("Getting the newest endpoint to save scan, which is now dead.")
        return endpoints.first()

    if count == 0:
        log.debug("Checking if there is a dead endpoint, given there where none alive.")
        dead_endpoints = Endpoint.objects.all().filter(
            url=url,
            ip_version=ip_version,
            port=port,
            protocol=protocol,
            is_dead=True).order_by('-discovered_on')

        if dead_endpoints.count():
            log.debug("Dead endpoint exists, getting latest to save scan")
            return dead_endpoints.first()

        log.debug("Creating dead endpoint to save scan to.")
        failmap_endpoint = Endpoint()
        failmap_endpoint.url = url
        failmap_endpoint.port = port
        failmap_endpoint.protocol = protocol
        failmap_endpoint.ip_version = ip_version
        failmap_endpoint.is_dead = True
        failmap_endpoint.is_dead_reason = message
        failmap_endpoint.is_dead_since = datetime.now(pytz.utc)
        failmap_endpoint.discovered_on = datetime.now(pytz.utc)
        failmap_endpoint.save()
        return failmap_endpoint


@app.task(queue='storage')
def scratch(domain, data):
    log.debug("Scratching data for %s", domain)
    scratchpad = TlsQualysScratchpad()
    scratchpad.domain = domain
    scratchpad.data = json.dumps(data)
    scratchpad.save()


# "smart" rate limiting
def endpoints_alive_in_past_24_hours(url):
    x = TlsQualysScan.objects.filter(endpoint__url=url,
                                     endpoint__port=443,
                                     endpoint__protocol__in=["https"],
                                     scan_date__gt=date().today() - timedelta(1)).exists()
    if x:
        log.debug("Scanned in past 24 hours: yes: %s", url.url)
    else:
        log.debug("Scanned in past 24 hours: no : %s", url.url)
    return x


def clean_endpoints(url, endpoints):
    """
    Kill all endpoints for this url

    :param endpoints: list of endpoints from qualys (from data['endpoints']), can be an empty list if nothing.
    :param url:
    :return: None
    """
    log.debug("Cleaning endpoints for: %s", url)

    ipv6 = sum([True for endpoint in endpoints if ":" in endpoint['ipAddress']])
    ipv4 = sum([True for endpoint in endpoints if ":" not in endpoint['ipAddress']])

    # if there are both ipv4 and ipv6 endpoints, then both have been created and nothing has to be set to dead.
    if ipv6 and not ipv4:
        endpoints = Endpoint.objects.all().filter(
            protocol="https",
            url=url,
            port=443,
            ip_version=4,
            is_dead=False).order_by('-discovered_on')
        for endpoint in endpoints:
            kill_endpoint(endpoint, "Only an IPv6 endpoint was returned, so this v4 endpoint didn't exist anymore.")

    if ipv4 and not ipv6:
        endpoints = Endpoint.objects.all().filter(
            protocol="https",
            url=url,
            port=443,
            ip_version=6,
            is_dead=False).order_by('-discovered_on')
        for endpoint in endpoints:
            kill_endpoint(endpoint, "Only an IPv4 endpoint was returned, so this v6 endpoint didn't exist anymore.")

    revive_url_if_possible(url)


def revive_url_if_possible(url):
    """
    A generic method that revives domains that have endpoints that are not dead.

    :return:
    """
    log.debug("Genericly attempting to revive url using endpoints from %s", url)

    if not url.is_dead and not url.not_resolvable:
        return

    # if there is an endpoint that is alive, make sure that the domain is set to alive
    # this should be a task of more generic endpoint management
    if TlsQualysScan.objects.filter(endpoint__is_dead=0, endpoint_url=url).exists():
        url.not_resolvable = False
        url.not_resolvable_since = datetime.now(pytz.utc)
        url.not_resolvable_reason = "Endpoints discovered during TLS Qualys Scan"
        url.is_dead = False
        url.is_deadsince = datetime.now(pytz.utc)
        url.is_dead_reason = "Endpoints discovered during TLS Qualys Scan"
        url.save()
