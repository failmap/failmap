# References:
# https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md
import ipaddress
import json
import logging
import sys
from datetime import date, datetime, timedelta
from random import randint
from time import sleep
from typing import List

import pytz
import requests
from django.core.exceptions import ObjectDoesNotExist

from failmap_admin.organizations.models import Url
from failmap_admin.scanners.models import Endpoint, TlsQualysScan, TlsQualysScratchpad

# Todo: use celery for distributed scanning, multiple threads. (within reason)
# Currently using a pool for scanning, which was way better than the fake queue solution.
# Todo: invalidate certificate name mismatches and self-signed certificates.
# done: when are dead domains rescanned, when are they really removed from the db? never.
# todo: check for network availability. What happens now?

"""
Todo: On network disconnect, the scanner hangs. Even though it's threaded... there is no end after
 the error callback.
:275  -- Requesting cached data from qualys for webmail.sittard-geleen.nl
:285  -- Assessments
:286  -- Max: 23
:287  -- Curr: 1
:288  -- Client: 23
:383  -- Scratching data for webmail.sittard-geleen.nl
:238  -- DNS: Got message: Resolving domain names
:275  -- Requesting cached data from qualys for webmail.sittard-geleen.nl
:285  -- Assessments
:286  -- Max: 24
:287  -- Curr: 1
:288  -- Client: 24
:383  -- Scratching data for webmail.sittard-geleen.nl
:252  -- Domain webmail.sittard-geleen.nl in progress. Endpoint: 93.95.250.242. Msgs: In progress
:275  -- Requesting cached data from qualys for webmail.sittard-geleen.nl
:285  -- Assessments
:286  -- Max: 24
:287  -- Curr: 1
:288  -- Client: 24
:383  -- Scratching data for webmail.sittard-geleen.nl
:252  -- Domain webmail.sittard-geleen.nl in progress. Endpoint: 93.95.250.242. Msgs: In progress
:275  -- Requesting cached data from qualys for webmail.sittard-geleen.nl
:294  -- something when wrong when scanning domain webmail.sittard-geleen.nl
:295  -- HTTPSConnectionPool(host='api.ssllabs.com', port=443): Max retries exceeded with url:
    /api/v2/analyze?host=webmail.sittard-geleen.nl&publish=off&startNew=off&fromCache=on&all=done
    (Caused by NewConnectionError('<requests.packages.urllib3.connection.VerifiedHTTPSConnection
    object at 0x1054bcc88>: Failed to establish a new connection: [Errno 60] Operation timed out',))
:296  -- Retrying 3 times, next in 20 seconds.
:294  -- something when wrong when scanning domain webmail.sittard-geleen.nl
:295  -- HTTPSConnectionPool(host='api.ssllabs.com', port=443): Max retries exceeded with url:
/api/v2/analyze?host=webmail.sittard-geleen.nl&publish=off&startNew=off&fromCache=on&all=done
(Caused by NewConnectionError('<requests.packages.urllib3.connection.VerifiedHTTPSConnection object
at 0x1054bc9b0>: Failed to establish a new connection: [Errno 51] Network is unreachable',))
:296  -- Retrying 2 times, next in 20 seconds.
:294  -- something when wrong when scanning domain webmail.sittard-geleen.nl
:295  -- HTTPSConnectionPool(host='api.ssllabs.com', port=443): Max retries exceeded with url:
/api/v2/analyze?host=webmail.sittard-geleen.nl&publish=off&startNew=off&fromCache=on&all=done
(Caused by NewConnectionError('<requests.packages.urllib3.connection.VerifiedHTTPSConnection object
at 0x105313908>: Failed to establish a new connection: [Errno 51] Network is unreachable',))
:296  -- Retrying 1 times, next in 20 seconds.
:383  -- Scratching data for webmail.sittard-geleen.nl
Error callback!
'NoneType' object has no attribute 'keys'
{}




^CProcess ForkPoolWorker-2051:
Process ForkPoolWorker-2050:
Process ForkPoolWorker-2049:
Process ForkPoolWorker-2047:
Process ForkPoolWorker-2045:
Process ForkPoolWorker-2046:
Process ForkPoolWorker-2048:
Traceback (most recent call last):


En zo voort:
154  -- Loaded 1 domains.
333  -- Requesting cached data from qualys for webmail.sittard-geleen.nl
352  -- something when wrong when scanning domain webmail.sittard-geleen.nl
353  -- EOF occurred in violation of protocol (_ssl.c:749)
354  -- Retrying 3 times, next in 20 seconds.
352  -- something when wrong when scanning domain webmail.sittard-geleen.nl
3  -- ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response',))
354  -- Retrying 2 times, next in 20 seconds.


^CProcess ForkPoolWorker-2050:


Soms ook ZONDER enige feedback, en daar kan je dan niet veel aan doen...
Dus wat nu? Een resume optie kan erg goed helpen... want je weet niet wanneer het gebeurd.
En je kan het verder ook niet meten...

File "/usr/local/Cellar/python3/3.6.0/Frameworks/Python.framework/Versions/3.6/lib/python3.6/
threading.py", line 1072, in _wait_for_tstate_lock
elif lock.acquire(block, timeout):

File "/usr/local/Cellar/python3/3.6.0/Frameworks/Python.framework/Versions/3.6/lib/python3.6/
threading.py", line 1072, in _wait_for_tstate_lock
elif lock.acquire(block, timeout):

Some other nice errors:

calculating score on 2017-09-06 08:23:22.714449+00:00 for beveiligd.harlingen.nl
Traceback (most recent call last):
File "/usr/local/lib/python3.6/site-packages/django/db/backends/base/base.py", line 211, in _commit
    return self.connection.commit()
sqlite3.OperationalError: database is locked

The above exception was the direct cause of the following exception:

Because of the development server, and using sqlite or something like that.
"""


class ScannerTlsQualys:
    """
    Manages endpoints:
     Protocols: https
     Ports: 443
     IP's: any related to a domain on mentioned protocols and ports.

    This scanner harvests endpoints during scan.

    This class will scan any domain it's asked to. It will rate limit on domains that have
    recently been scanned to not flood qualys (and keep in good standing). A scan at qualys
    takes about 1 to 10 minutes. This script will make sure requests are not done too quickly.

    This class can scan domains in bulk. All endpoints related to these scans are set on pending
    before the scan starts. The caller of this class has to manage what URL's are scanned, when,
    especially when handling new domains without endpoints to set to pending problems may occur
    (problems = multiple scanners trying to scan the same domain at the same time).

    Scans and grading is done by Qualys: it's their view of the internet, which might differ
    from yours.

    """

    rate_limit = True
    log = None

    # All proposed solutions to remove duplicate output don't work.
    # using the terrible handlers = [] solution.
    # It seems that these objects remain even if a new class is made, i lack python skills or this
    # is a surprise. Never expected it.
    # http://stackoverflow.com/questions/31403679/
    #       python-logging-module-duplicated-console-output-ipython-notebook-qtconsole#31404725
    # instead of using a custom colored log solution, we're using the standard log.

    def __init__(self):
        ScannerTlsQualys.log = logging.getLogger(__package__)
        ScannerTlsQualys.log.debug("Logging initialized")

    @staticmethod
    def scan(domains: List[str]):
        """
        Scans a list of domains. Skipping all that have been scanned in the past 24 hours and
        starting each scan about every 30 seconds.
        :param domains:
        :return:
        """

        from multiprocessing import Pool
        pool = Pool(processes=7)  # max 7 concurrent scans

        domains = ScannerTlsQualys.external_service_task_rate_limit(domains)
        ScannerTlsQualys.log.debug("Loaded %s domains.", len(domains))

        # if you want to run this from multiple domains, you'd need celery still.
        # which we now can upgrade to.
        # with 30 seconds per domain, you can only scan 2800 domains a day...
        # Even while the headers  X-Max-Assessments and X-Current-Assessments
        # give the idea you might have 25 scans at the same time, it's not.
        # the amount actually lowers. Starting a new scan every 20 seconds the scan
        # results in there is not enough room after 30 minutes. So you need to start
        # scans slower. Event with 30 seconds it's too fast. So just do 60.

        # todo: add keyboard interrupt handler.
        # todo: figure out why it's not parallel anymore.
        try:
            for domain in domains:
                pool.apply_async(ScannerTlsQualys.scantask, [domain],
                                 callback=ScannerTlsQualys.success_callback,
                                 error_callback=ScannerTlsQualys.error_callback)
                # ScannerTlsQualys.scantask(domain) # old sequential approach
                ScannerTlsQualys.log.debug("Applying rate limiting, waiting max 70 seconds.")
                sleep(60 + randint(0, 10))  # Start a new task, but don't pulsate too much.
        except KeyboardInterrupt:
            ScannerTlsQualys.log.info("Received keyboard interrupt, waiting for scan to end.")

        ScannerTlsQualys.log.debug("Closing pool")
        pool.close()
        ScannerTlsQualys.log.debug("Joining pool")
        pool.join()  # possible cause of locks, solution: set thread timeout. A scan max takes 5 min
        ScannerTlsQualys.log.debug("Done")

    @staticmethod
    def success_callback(x):
        ScannerTlsQualys.log.debug("Success!")

    @staticmethod
    def error_callback(x):
        ScannerTlsQualys.log.error("Error callback!")
        ScannerTlsQualys.log.error(x)
        ScannerTlsQualys.log.error(vars(x))
        # we're getting a statusDetails back... probably not handled by the code

    # max N at the same time? how to?
    # what happens when there is no internet?
    @staticmethod
    def scantask(domain):
        """
        Carries out a scan until the ERROR or READY is returned. There will be many checks performed
        by the scanner, signalled by TESTING_ messages. There also are many DNS messages when
        starting the scan.

        A scan usually takes about two minutes.

        :param domain: string representing an url, without protocol or port.
        :return:
        """
        ScannerTlsQualys.log.info("Starting scan on: %s" % domain)

        data = {'status': "NEW"}

        while data['status'] != "READY" and data['status'] != "ERROR":
            data = ScannerTlsQualys.service_provider_scan_via_api(domain)
            ScannerTlsQualys.scratch(domain, data)  # for debugging
            ScannerTlsQualys.report_to_console(domain, data)  # for more debugging

            if 'status' in data.keys():
                if data['status'] == "READY" and 'endpoints' in data.keys():
                    ScannerTlsQualys.save_scan(domain, data)
                    ScannerTlsQualys.clean_endpoints(domain, data['endpoints'])
                    return

                # in nearly all cases the domain could not be retrieved, so clean the endpoints
                # and move on. As the result was "error", over internet, you should not need to
                # check if there is an internet connection... obviously
                # we can believe that if the scanner says "unable to resolve domain name"
                # that this is true. We will kill the domain then.
                # todo: make the url unresolvable?
                if data['status'] == "ERROR":
                    ScannerTlsQualys.scratch(domain, data)  # we always want to see what happened.
                    ScannerTlsQualys.clean_endpoints(domain, [])
                    return

            else:
                data['status'] = "FAILURE"  # stay in the loop
                ScannerTlsQualys.log.error("Unexpected result from API")
                ScannerTlsQualys.log.error(data)  # print for debugging purposes
                ScannerTlsQualys.scratch(domain, data)  # we always want to see what happened.

            # https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md
            # it doesn't matter how fast you ask the status, it doesnt' get "ready" sooner.
            # so, just ask that every 20 seconds.
            sleep(20 + randint(0, 4))  # don't pulsate.

    @staticmethod
    def external_service_task_rate_limit(domains):
        """
        Why rate limiting the domains to scan?:
        Qualys is an external, free, service that can only handle a finite amount of scans.
        The fewer, the better.

        Therefore we will not scan domains that: have been scanned in the past 24 hours.
        Will only scan domains that have been dead longer than a month.

        :param domains: list of domains
        :return: unique set of domains that are alive...
        """
        domains_to_scan = list()  # list has uniques?

        # we are not checking if the domain is dead at all... we're just doing what is asked.
        # we do manage some endpoints (https, http on port 443)
        for domain in domains:
            if not ScannerTlsQualys.endpoints_alive_in_past_24_hours(domain):
                domains_to_scan.append(domain)

        # todo: we can use tldextract to verify the correctness of domains. (not ip's)
        domains = domains_to_scan
        domains_to_scan = list()
        # check if the domain is... sort of valid...
        for domain in domains:
            if len(domain) > 3:
                domains_to_scan.append(domain)

        # prevent duplicates
        domains_to_scan = set(domains_to_scan)
        return list(domains_to_scan)

    @staticmethod
    def report_to_console(domain, data):
        """
        Gives some impression of what is currently going on in the scan.

        This will show a lot of DNS messages, which means that SSL Labs is working on it.
        It would be easier to ask the scan status. But well... this also works.

        Another error is "Too many new assessments too fast. Please slow down.", this means
        the logic above for starting scans is not correct (or scans are not distributed enough).

        :param domain:
        :param data:
        :return:
        """
        if 'status' in data.keys():
            if data['status'] == "READY":
                for endpoint in data['endpoints']:
                    if 'grade' in endpoint.keys():
                        ScannerTlsQualys.log.debug("%s (%s) = %s" %
                                                   (domain, endpoint['ipAddress'],
                                                    endpoint['grade']))
                    else:
                        ScannerTlsQualys.log.debug("%s = No TLS (0)" % domain)
                        ScannerTlsQualys.log.debug("Message: %s" % endpoint['statusMessage'])  # new

            if data['status'] == "DNS" or data['status'] == "ERROR":
                if 'statusMessage' in data.keys():
                    ScannerTlsQualys.log.debug("%s: Got message: %s", data['status'],
                                               data['statusMessage'])
                else:
                    ScannerTlsQualys.log.debug("%s: Got message: %s", data['status'], data)

            if data['status'] == "IN_PROGRESS":
                for endpoint in data['endpoints']:
                    # statusDetails was deprecated?
                    # if 'statusDetails' in endpoint.keys():
                    #     ScannerTlsQualys.log.debug(
                    #        "Domain %s in progress. Endpoint: %s. Msg: %s "
                    #        % (domain, endpoint['ipAddress'], endpoint['statusDetails']))
                    if 'statusMessage' in endpoint.keys():
                        ScannerTlsQualys.log.debug(
                            "Domain %s in progress. Endpoint: %s. Msgs: %s "
                            % (domain, endpoint['ipAddress'], endpoint['statusMessage']))
                    else:
                        ScannerTlsQualys.log.debug(
                            "Domain %s in progress. Endpoint: %s. "
                            % (domain, endpoint['ipAddress']))
        else:
            # no idea how to handle this, so dumping the data...
            # ex: {'errors': [{'message': 'Concurrent assessment limit reached (7/7)'}]}
            ScannerTlsQualys.log.debug("Unexpected data received")
            ScannerTlsQualys.log.debug(data)

    @staticmethod
    def service_provider_scan_via_api(domain):
        """
        Qualys parameters

        # publish: off, it's friendlier to the domains scanned
        # startnew: off, that's done automatically when needed by service provider
        # fromcache: on: they are chached for a few hours only.

        :param domain:
        :return:
        """
        ScannerTlsQualys.log.debug("Requesting cached data from qualys for %s", domain)
        payload = {'host': domain, 'publish': "off", 'startNew': "off",
                   'fromCache': "on", 'all': "done"}

        retries = 3

        # todo: this can lead up to too many scans at the same time... or does the pool limit this?
        while retries > 0:
            try:
                response = requests.get("https://api.ssllabs.com/api/v2/analyze", params=payload)
                ScannerTlsQualys.log.debug("Assessments")
                ScannerTlsQualys.log.debug("Max: %s", response.headers['X-Max-Assessments'])
                ScannerTlsQualys.log.debug("Curr: %s", response.headers['X-Current-Assessments'])
                ScannerTlsQualys.log.debug("Client: %s", response.headers['X-ClientMaxAssessments'])
                # ScannerTlsQualys.log.debug(vars(response))  # extreme debugging
                return response.json()
            except requests.RequestException as e:
                # ex: ('Connection aborted.', ConnectionResetError(54, 'Connection reset by peer'))
                # ex: EOF occurred in violation of protocol (_ssl.c:749)
                ScannerTlsQualys.log.debug("something when wrong when scanning domain %s", domain)
                ScannerTlsQualys.log.debug(e)
                ScannerTlsQualys.log.debug("Retrying %s times, next in 20 seconds.", retries)
                sleep(20)
                retries = retries - 1

    # todo: django.db.utils.IntegrityError: NOT NULL constraint failed: .endpoint_id
    @staticmethod
    def save_scan(domain, data):
        """
        Saves another scan to the database. Does some endpoint plumbing.
        :param domain:
        :param data: raw JSON data from qualys
        :return:
        """
        ScannerTlsQualys.log.debug("Trying to save scan for %s", domain)

        # manage endpoints
        # Based on the response by Qualys.
        # An endpoint of the same IP could already exist and be dead. Keep it dead.
        # An endpoint can be made dead by not appearing in this list (cleaning)
        # or when qualys says so.
        for qualys_endpoint in data['endpoints']:

            # removes duplicates
            # declares endpoints dead if need be
            # created endpoints, etc.
            # always returns a single endpoint
            failmap_endpoint = ScannerTlsQualys.manage_endpoint(qualys_endpoint, domain)

            # save scan for the endpoint
            # get the most recent scan of this endpoint, if any and work with that to save data.
            # data is saved when the rating didn't change, otherwise a new record is created.
            scan = TlsQualysScan.objects.filter(endpoint=failmap_endpoint). \
                order_by('-scan_moment').first()

            rating = qualys_endpoint['grade'] if 'grade' in qualys_endpoint.keys() else 0
            rating_no_trust = qualys_endpoint['gradeTrustIgnored'] \
                if 'gradeTrustIgnored' in qualys_endpoint.keys() else 0

            if scan:
                ScannerTlsQualys.log.debug("There was already a scan on this endpoint.")

                if scan.qualys_rating == rating and scan.qualys_rating_no_trust == rating_no_trust:
                    ScannerTlsQualys.log.info("Scan on %s did not alter the rating, "
                                              "updating scan date only." % failmap_endpoint)
                    scan.scan_moment = datetime.now(pytz.utc)
                    scan.scan_time = datetime.now(pytz.utc)
                    scan.scan_date = datetime.now(pytz.utc)
                    scan.qualys_message = qualys_endpoint['statusMessage']
                    scan.save()

                else:
                    ScannerTlsQualys.log.info("Rating changed on %s, "
                                              "we're going to save the scan to retain history"
                                              % failmap_endpoint)
                    scan = TlsQualysScan()
                    scan.endpoint = failmap_endpoint
                    scan.qualys_rating = rating
                    scan.qualys_rating_no_trust = rating_no_trust
                    scan.scan_moment = datetime.now(pytz.utc)
                    scan.scan_time = datetime.now(pytz.utc)
                    scan.scan_date = datetime.now(pytz.utc)
                    scan.rating_determined_on = datetime.now(pytz.utc)
                    scan.qualys_message = qualys_endpoint['statusMessage']
                    scan.save()

            else:
                # todo: don't like to have the same code twice.
                ScannerTlsQualys.log.info("This endpoint on %s was never scanned, "
                                          "creating a new scan." % failmap_endpoint)
                scan = TlsQualysScan()
                scan.endpoint = failmap_endpoint
                scan.qualys_rating = rating
                scan.qualys_rating_no_trust = rating_no_trust
                scan.scan_moment = datetime.now(pytz.utc)
                scan.scan_time = datetime.now(pytz.utc)
                scan.scan_date = datetime.now(pytz.utc)
                scan.rating_determined_on = datetime.now(pytz.utc)
                scan.qualys_message = qualys_endpoint['statusMessage']
                scan.save()

    @staticmethod
    def manage_endpoint(qualys_endpoint, domain):
        """Manages this endpoint, and returns a failmap_endpoint to work with."""

        # expect that it exists
        status_message = qualys_endpoint['statusMessage']

        # todo: message: "Failed to communicate with the secure server"
        ScannerTlsQualys.log.debug("Managing endpoint with message '%s'" % status_message)

        """
        IP address is from private address space (RFC 1918)
        Means endpoint cannot be scanned by qualys. So we set it as non-resolvable (the http scanner
        will set it to resolvable again, and so we've to check ip's now before scanning here).
        At least the thread will not crash.
        todo: 10.210.9.2, 10/8 etc will not be scanned, we should check for that.
        """
        # Unable to connect to server? Declare endpoint dead.
        # The endpoint probably has another port / service than https/443
        if status_message == "Unable to connect to the server" or \
           status_message == "Failed to communicate with the secure server" or \
           status_message == "Unexpected failure" or \
           status_message == "IP address is from private address space (RFC 1918)":
            return ScannerTlsQualys. \
                endpoint_could_not_connect_to_server(qualys_endpoint, domain, status_message)

        # todo: handle No secure protocols supported correctly. It is a weird state (https, notls?)
        if status_message == "Ready" or \
           status_message == "Certificate not valid for domain name" or \
           status_message == "No secure protocols supported":
            return ScannerTlsQualys. \
                failmap_endpoint_ratings_received(qualys_endpoint, domain)

    @staticmethod
    def failmap_endpoint_ratings_received(qualys_endpoint, domain):
        # we only store compressed ipv6 addresses. Qualys returns a weird format: abcd:0:0:0:...
        # so we're going to compress it here
        qualys_endpoint['ipAddress'] = ipaddress.ip_address(qualys_endpoint['ipAddress']).compressed

        # Manage endpoint
        # Endpoint exists? If not, make it,
        endpoints = Endpoint.objects.all().filter(domain=domain,
                                                  ip=qualys_endpoint['ipAddress'],
                                                  port=443,
                                                  protocol="https",
                                                  is_dead=False)
        # 0: make new endpoint, representing the current result
        # 1: update the endpoint with the current information
        # >1: everything matches, it's basically the same endpoint and it can be merged.
        count = endpoints.count()

        if count == 0:
            ScannerTlsQualys.log.debug("This endpoint is new: %s %s:443" %
                                       (domain, qualys_endpoint['ipAddress']))

            # Multiple organizations can have the same URL. However, this is rare and has
            # not happened yet in the Netherlands:
            # it's not OK to have multiple processors of sensitive data to all enter at the
            # same entry point. If so, we need to prove that this is actually the case.
            # and we usually can't without research.
            # It remains a todo that multiple organizations use the same URL. For now
            # we say this is not the case.
            failmap_endpoint = Endpoint()
            try:
                failmap_endpoint.url = Url.objects.filter(url=domain).first()  # todo: see above
            except ObjectDoesNotExist:
                failmap_endpoint.url = ""
            failmap_endpoint.domain = domain  # not used anymore. Filled for legacy reasons.
            failmap_endpoint.port = 443
            failmap_endpoint.protocol = "https"
            failmap_endpoint.ip = qualys_endpoint['ipAddress']
            failmap_endpoint.is_dead = False
            failmap_endpoint.discovered_on = datetime.now(pytz.utc)
            failmap_endpoint.save()

        if count > 1:
            ScannerTlsQualys.log.debug("Multiple similar endpoints detected for %s" % domain)
            ScannerTlsQualys.log.debug("Flattening similar endpoints to a single one.")

            # now merge all of these endpoints into one by transfering all
            # associations of this endpoint to the first endpoint.
            # https://docs.djangoproject.com/en/1.11/topics/db/queries/
            failmap_endpoint = endpoints.first()  # the saved one
            # and the rest, except for the first is deleted
            for endpoint in endpoints:

                # but keep the first endpoint. Don't know if this comparison is valid.
                if endpoint == failmap_endpoint:
                    continue

                # in the future there might be other scans too... be warned
                scans = TlsQualysScan.objects.all().filter(endpoint=endpoint)
                for scan in scans:
                    scan.endpoint = failmap_endpoint
                    scan.save()
                endpoint.delete()

        if count == 1:
            ScannerTlsQualys.log.debug("An endpoint exists already, using this")
            # just one existing endpoint. Since we got it back it's alive.
            failmap_endpoint = endpoints[0]

        return failmap_endpoint

    @staticmethod
    # Server does not have HTTPS.
    def endpoint_could_not_connect_to_server(qualys_endpoint, domain, status_message):
        ScannerTlsQualys.log.debug("Handing could not connect to server")
        # If this endpoint exists and is alive, mark it as dead: port 443 does not
        # do anything.
        qualys_endpoint['ipAddress'] = ipaddress.ip_address(qualys_endpoint['ipAddress']).compressed

        alive_endpoints = Endpoint.objects.all().filter(
            domain=domain,
            ip=qualys_endpoint['ipAddress'],
            port=443,
            protocol="https",
            is_dead=False).order_by('-discovered_on')
        # should be one, might be multiple due to human error.
        for ep in alive_endpoints:
            ep.is_dead = True
            ep.is_dead_since = datetime.now(pytz.utc)
            ep.is_dead_reason = status_message
            ep.save()

        # if there is no end point at all, add one, so we know port 443 is not available
        if alive_endpoints.count():
            ScannerTlsQualys.log.debug("Getting the newest endpoint to save scan.")
            failmap_endpoint = alive_endpoints.first()
        else:
            ScannerTlsQualys.log.debug("Checking if there is a dead endpoint.")
            dead_endpoints = Endpoint.objects.all().filter(
                domain=domain,
                ip=qualys_endpoint['ipAddress'],
                port=443,
                protocol="https",
                is_dead=True).order_by('-discovered_on')

            if dead_endpoints.count():
                ScannerTlsQualys.log.debug("Dead endpoint exists, getting latest to save scan")
                failmap_endpoint = dead_endpoints.first()
            else:
                ScannerTlsQualys.log.debug("Creating dead endpoint to save scan to.")
                failmap_endpoint = Endpoint()
                try:
                    failmap_endpoint.url = Url.objects.filter(
                        url=domain).first()  # todo: below
                except ObjectDoesNotExist:
                    failmap_endpoint.url = ""
                failmap_endpoint.domain = domain
                failmap_endpoint.port = 443
                failmap_endpoint.protocol = "https"
                failmap_endpoint.ip = qualys_endpoint['ipAddress']
                failmap_endpoint.is_dead = True
                failmap_endpoint.is_dead_reason = status_message
                failmap_endpoint.is_dead_since = datetime.now(pytz.utc)
                failmap_endpoint.discovered_on = datetime.now(pytz.utc)
                failmap_endpoint.save()

        return failmap_endpoint

    @staticmethod
    def scratch(domain, data):
        ScannerTlsQualys.log.debug("Scratching data for %s", domain)
        scratch = TlsQualysScratchpad()
        scratch.domain = domain
        scratch.data = json.dumps(data)
        scratch.save()

    # smart rate limiting
    @staticmethod
    def endpoints_alive_in_past_24_hours(domain):
        x = TlsQualysScan.objects.filter(endpoint__domain=domain,
                                         endpoint__port=443,
                                         endpoint__protocol__in=["https"],
                                         scan_date__gt=date.today() - timedelta(1)).exists()
        if x:
            ScannerTlsQualys.log.debug("domain %s was scanned in past 24 hours", domain)
        else:
            ScannerTlsQualys.log.debug("domain %s was NOT scanned in past 24 hours", domain)
        return x

    @staticmethod
    def clean_endpoints(domain, endpoints):
        """
        Clean's up endpoints that where not found in a scan.

        For example:
        Hilversum, who had two ip's on a domain, decided that one was enough.
        The removed endpoint had an F, thus it was marked red, yet they didn't use it anymore.

        If there are no endpoints found in the qualys scan, all the endpoints ending on 443
        with the http or https protocol are set to dead.

        :param endpoints: list of endpoints from qualys
        :param domain: domain.com
        :return: None
        """
        ScannerTlsQualys.log.debug("Cleaning endpoints for %s", domain)

        # normalize ip's
        for endpoint in endpoints:
            endpoint['ipAddress'] = ipaddress.ip_address(endpoint['ipAddress']).compressed

        # list of addresses that we're NOT going to declare dead :)
        ip_addresses = []
        for endpoint in endpoints:
            ip_addresses.append(endpoint['ipAddress'])

        e = Endpoint
        # bugfix: the result of the filter was not stored in e.So all endpoints where set to deleted
        # exclude was in a separate assignment.
        # 2017-0 -- scanner_tls_qualys.py:334  -- Cleaning endpoints for mail.albrandswaard.nl
        # 2017-Found an endpoint that can get killed: webmail.alkmaar.nl
        # above should not be possible...

        killable_endpoints = e.objects.filter(is_dead=0,
                                              domain=domain,
                                              port=443,
                                              protocol="https").exclude(ip__in=ip_addresses)

        for killable_endpoint in killable_endpoints:
            ScannerTlsQualys.log.debug('Found an endpoint that can get killed: %s',
                                       killable_endpoint.domain)
            killable_endpoint.is_dead = True
            killable_endpoint.is_dead_since = datetime.now(pytz.utc)
            killable_endpoint.is_dead_reason = "Endpoint not found anymore in qualys scan."
            killable_endpoint.save()

        ScannerTlsQualys.revive_url_with_alive_endpoints(domain)

    @staticmethod
    def revive_url_with_alive_endpoints(domain):
        """
        A generic method that revives domains that have endpoints that are not dead.

        The domain is then revived by force.

        :return:
        """
        ScannerTlsQualys.log.debug("Genericly attempting to revive url using endpoints from %s",
                                   domain)

        # if there is an endpoint that is alive, make sure that the domain is set to alive
        # this should be a task of more generic endpoint management
        if TlsQualysScan.objects.filter(endpoint__is_dead=0, endpoint__domain=domain).exists():
            urls = Url.objects.filter(url=domain, is_dead=True)

            for url in urls:
                url.is_dead = False
                url.is_deadsince = datetime.now(pytz.utc)
                url.is_dead_reason = "There are endpoints discovered via scanner tls qualys"
                url.save()  # might be empty, which is fine...

                # the reverse is not always true: while you can genericly revive domains if there is
                # a
                # working endpoint. This scanner can not kill the domain if there is no TLS.
                # However, you can IF there are no other endpoints and there is no TLS endpoint.
                # after scanning a few times. ... There are a few domains in limbo: those who have
                # no endpoints, that have been scanned, but may be visited by other scanners...
                # This scanner doesn't check if the domain is dead (or exists at al) the benefit is
                # that
                # you can still re-check a domain by scanning it. So make sure the list of domains
                # to be
                # scanned is good enough... So let's kill some urls...

                # if an url has NO endpoints,
