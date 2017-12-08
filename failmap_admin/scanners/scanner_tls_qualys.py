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
from random import randint
from time import sleep
from typing import List

import pytz
import requests
from celery import group
from django.core.exceptions import ObjectDoesNotExist

from failmap_admin.organizations.models import Organization, Url
from failmap_admin.scanners.models import (Endpoint, EndpointGenericScan, TlsQualysScan,
                                           TlsQualysScratchpad)
from failmap_admin.scanners.scanner_http import store_url_ips
from failmap_admin.scanners.state_manager import StateManager

from ..celery import PRIO_HIGH, PRIO_NORMAL, app

log = logging.getLogger(__name__)


def scan_url_list(urls: List[Url]):
    urls = external_service_task_rate_limit(urls)
    log.debug("Domains to scan: %s", len(urls))

    # warning: qualys allows 1 scan per minute (probably per IP)
    for url in urls:
        scan_task(url)
        log.debug("Rate limit: +/- 70 seconds.")
        sleep(60 + randint(0, 10))  # Start a new task, but don't pulsate too much.


@app.task
def scan_urls(urls: List[Url], execute: bool=True, priority: int=PRIO_NORMAL):
    urls = external_service_task_rate_limit(urls)

    """Compose and execute taskset to scan specified urls."""
    try:
        task = compose(urls=urls)
        return task.apply_async(priority=priority) if execute else task
    except (ValueError, Endpoint.DoesNotExist):
        log.error('Could not schedule scans, due to error reported above.')


def scan_multithreaded(urls: List[Url]):
        from multiprocessing import Pool
        pool = Pool(processes=4)

        for url in urls:
            pool.apply_async(scan_task, [url])
            sleep(60)


def compose(organizations: List[Organization]=None, urls: List[Url]=None):
    """Compose taskset to scan specified organizations or urls (not both)."""

    if not any([organizations, urls]):
        log.error('No organizations or urls supplied.')
        raise ValueError("No organizations or urls supplied.")

    # collect all scannable urls for provided organizations
    if organizations:
        urls_organizations = Url.objects.all().filter(is_dead=False,
                                                      not_resolvable=False,
                                                      organization__in=organizations)

        urls = list(urls_organizations) + urls if urls else list(urls_organizations)

    # create a group of parallel executable scan&store tasks for all endpoints
    taskset = group(scan_task.s(url) for url in urls)

    return taskset


@app.task(
    # http://docs.celeryproject.org/en/latest/userguide/tasks.html#Task.rate_limit
    # start at most 1 qualys task per minute to not get our IP blocked

    # After starting a scan you can read it out as much as you want. The problem lies with rate limiting
    # of starting the task.

    # Creating a new task means it will be placed somewhere on the queue.
    rate_limit='1/m',
)
def scan_task(url):

    # start the scan (or read out the cache, which is a bit inefficient)
    # data = service_provider_scan_via_api(url.url)

    log.info("Starting scan on: %s" % url.url)
    readout = scan_readout_task.s(url)
    # and so you're still waiting synchronously.
    # this will create a new task, that should be read out pretty quickly (there is a deadline of about 10 minutes)
    readout.apply_async()


@app.task(
    # after starting a scan (1/m) you can read out every 20 seconds.
    # You can do so in the 10 minutes. If you don't, it will start a new scan which affects your rate limit.
    bind=True
)
def scan_readout_task(self, url):
    """
    Carries out a scan until the ERROR or READY is returned. There will be many checks performed
    by the scanner, signalled by TESTING_ messages. There also are many DNS messages when
    starting the scan.

    A scan usually takes about two minutes. It _can_ take much longer depending on the amount
    of ip's qualys is able to find. Having eight different IP's is not special for some cloud
    hosters.

    You can have about 25 scans running at the same time: with overlap. So you cannot start
    25 scans at the same time(!).

    :param url: object representing an url
    :return:
    """

    data = service_provider_scan_via_api(url.url)
    scratch(url.url, data)  # for debugging
    report_to_console(url.url, data)  # for more debugging

    if 'status' in data.keys():
        if data['status'] == "READY" and 'endpoints' in data.keys():
            result = save_scan(url, data)
            clean_endpoints(url, data['endpoints'])
            return '%s %s' % (url, result)

        if data['status'] == "ERROR":
            """
            Error is usually "unable to resolve domain". This should kill the endpoint(s).
            """
            scratch(url, data)  # we always want to see what happened.
            clean_endpoints(url, [])
            return

    else:
        data['status'] = "FAILURE"  # stay in the loop
        log.error("Unexpected result from API")
        log.error(data)  # print for debugging purposes
        scratch(url, data)  # we always want to see what happened.

    """
    While the documentation says to check every 10 seconds, we'll do that between every
    20 to 25, simply because it matters very little when scans are ran parralel.
    https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md
    """
    log.info('Still waiting for Qualys result. Retrying task in 20 seconds.')
    # 10 minutes of retries... (20s seconds * 30 = 10 minutes)
    raise self.retry(countdown=20, priorty=PRIO_HIGH, max_retries=30)
    # sleep(20 + randint(0, 5))  # don't pulsate.


def external_service_task_rate_limit(urls):
    """
    The fewer scans we run, the better. So try to limit the amount of domains we need to scan by:
    - not scanning an url that has been scanned in the past 24 hours.
    - removing duplicates
    - really basic input validation

    todo: use tldextract to verify the correctness of domains. (not ip's)

    :param urls: list of domains
    :return: unique set of domains that are alive
    """

    urls = [url for url in urls if len(url.url) > 3]  # fake input validation
    urls = [url for url in urls if not endpoints_alive_in_past_24_hours(url)]
    return list(set(urls))  # remove duplicates


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
    """
    Qualys parameters

    https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md

    # publish: off, it's friendlier to the domains scanned
    # startnew: off, that's done automatically when needed by service provider
    # fromcache: on: they are chached for a few hours only.
    # ignoreMismatch: on: continue a scan, even if the certificate is for another domain

    :param domain:
    :return:
    """
    log.debug("Requesting cached data from qualys for %s", domain)
    payload = {'host': domain,
               'publish': "off",
               'startNew': "off",
               'fromCache': "off",  # cache can have mismatches, but is ignored when startnew
               'ignoreMismatch': "on",
               'all': "done"}

    retries = 3

    # todo: this can lead up to too many scans at the same time... or does the pool limit this?
    while retries > 0:
        try:
            response = requests.get("https://api.ssllabs.com/api/v2/analyze", params=payload)
            # log.debug(vars(response))  # extreme debugging
            log.debug("Running assessments: max: %s, current: %s, client: %s" % (
                response.headers['X-Max-Assessments'],
                response.headers['X-Current-Assessments'],
                response.headers['X-ClientMaxAssessments']
            ))
            return response.json()
        except requests.RequestException as e:
            # ex: ('Connection aborted.', ConnectionResetError(54, 'Connection reset by peer'))
            # ex: EOF occurred in violation of protocol (_ssl.c:749)
            log.error("something when wrong when scanning domain %s", domain)
            log.error(e)
            log.error("Retrying %s times, next in 20 seconds.", retries)
            sleep(20)
            retries = retries - 1


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
                                     scan_date__gt=date.today() - timedelta(1)).exists()
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


@app.task
def scan():
    # todo: sort the organizations on the oldest scanned first, or never scanned first.
    # or make a separate part that first scans all never scanned stuff, per organization
    # so new stuff has some priority.

    # Not something that influenced from random scans from the admin interface.
    # scan per organization, to lower the amount of time for updates on the map
    # after the scan finished, update the ratings for the urls and then the organization.

    # https://stackoverflow.com/questions/13694034/is-a-python-list-guaranteed-to-have-its-
    # elements-stay-in-the-order-they-are-inse
    resume = StateManager.create_resumed_organizationlist(scanner="ScannerTlsQualys")

    for organization in resume:
        StateManager.set_state("ScannerTlsQualys", organization.name)
        scan_organization.s(organization).apply()


@app.task
def scan_organization(organization):
    """

    :return: list of url objects
    """
    # This scanner only scans urls with endpoints (because we inner join endpoint_is_dead)

    # Using the HTTP scanner, it's very easy and quick to see if a url resolves.
    # This is much faster than waiting 1.5 minutes for qualys to figure it out.
    # So we're only scanning what we know works.
    log.info("Scanning organization: %s" % organization)

    urls = Url.objects.filter(organization=organization,
                              is_dead=False,
                              not_resolvable=False,
                              endpoint__is_dead=False,
                              endpoint__protocol="https",
                              endpoint__port=443)

    if not urls:
        log.info("There are no alive https urls for this organization: %s" % organization)
        return

    # don't rebuild the ratings. It's hard to get right with chords and such.
    # we want all scan_url tasks to be finished when running the other tasks (as immutable, with task.si).
    # the "issue" now is that scan_urls says True because all urls have been added (but not read)
    scan_urls(urls=urls, priority=PRIO_NORMAL)

    # we have rebuild ratings done periodically. That works better.
    # rerate_urls(myurls)
    # add_organization_rating(organizations=[organization])


# this is an anti-pattern: any new url should be scanned when added, not via a separate clunky process.
# currently this should be run every hour. Prio should be higher than normal scans, but not highest.
@app.task
def scan_new_urls():
    # find urls that don't have an qualys scan and are resolvable on https/443
    # todo: perhaps find per organization, so there will be less ratings? (rebuilratings cleans)
    # ah, this finds both ipv4 and 6 endpoints, since this is done in batches it doesn't
    # really matter (yet).
    urls = Url.objects.filter(is_dead=False,
                              not_resolvable=False,
                              endpoint__port=443,
                              endpoint__protocol="https"
                              ).exclude(endpoint__tlsqualysscan__isnull=False)

    if urls.count() < 1:
        log.info("There are no new urls.")
        return

    log.info("Good news! There are %s urls to scan!" % urls.count())
    pie = """
                                        (
                   (
           )                    )             (
                   )           (o)    )
           (      (o)    )     ,|,            )
          (o)     ,|,          |~\    (      (o)
          ,|,     |~\    (     \ |   (o)     ,|,
          \~|     \ |   (o)    |`\   ,|,     |~\\
          |`\     |`\@@@,|,@@@@\ |@@@\~|     \ |
          \ | o@@@\ |@@@\~|@@@@|`\@@@|`\@@@o |`\\
         o|`\@@@@@|`\@@@|`\@@@@\ |@@@\ |@@@@@\ |o
       o@@\ |@@@@@\ |@@@\ |@@@@@@@@@@|`\@@@@@|`\@@o
      @@@@|`\@@@@@@@@@@@|`\@@@@@@@@@@\ |@@@@@\ |@@@@
      p@@@@@@@@@@@@@@@@@\ |@@@@@@@@@@|`\@@@@@@@@@@@q
      @@o@@@@@@@@@@@@@@@|`\@@@@@@@@@@@@@@@@@@@@@@o@@
      @:@@@o@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@o@@::@
      ::@@::@@o@@@@@@@@@@@@@@@@@@@@@@@@@@@@o@@:@@::@
      ::@@::@@@@::oo@@@@oo@@@@@ooo@@@@@o:::@@@::::::
      %::::::@::::::@@@@:::@@@:::::@@@@:::::@@:::::%
      %%::::::::::::@@::::::@:::::::@@::::::::::::%%
      ::%%%::::::::::@::::::::::::::@::::::::::%%%::
    .#::%::%%%%%%:::::::::::::::::::::::::%%%%%::%::#.
  .###::::::%%:::%:%%%%%%%%%%%%%%%%%%%%%:%:::%%:::::###.
.#####::::::%:::::%%::::::%%%%:::::%%::::%::::::::::#####.
.######`:::::::::::%:::::::%:::::::::%::::%:::::::::'######.
.#########``::::::::::::::::::::::::::::::::::::''#########.
`.#############```::::::::::::::::::::::::'''#############.'
`.######################################################.'
  ` .###########,._.,,,. #######<_\##################. '
     ` .#######,;:      `,/____,__`\_____,_________,_____
        `  .###;;;`.   _,;>-,------,,--------,----------'
            `  `,;' ~~~ ,'\######_/'#######  .  '
                ''~`''''    -  .'/;  -    '       -Catalyst
    """
    log.info(pie)

    log.debug("These are the new urls:")
    for url in urls:
        log.debug(url)

    import math

    # Scan the new urls per 30, which takes about 30 minutes.
    # Why: so scans will still be multi threaded and the map updates frequently
    #      and we have a little less ratings if multiple urls are from one organization
    batch_size = 30
    log.debug("Scanning new urls in batches of: %s" % batch_size)
    i = 0
    iterations = int(math.ceil(len(urls) / batch_size))
    while i < iterations:
        log.info("New batch %s: from %s to %s" % (i, i * batch_size, (i + 1) * batch_size))
        myurls = urls[i * batch_size:(i + 1) * batch_size]
        i = i + 1
        scan_urls(myurls, priority=PRIO_HIGH)

    return urls
