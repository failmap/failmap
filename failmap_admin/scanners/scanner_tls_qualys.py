# References:
# https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md

# Todo: use celery for distributed scanning, multiple threads. (within reason)
# Currently using a pool for scanning, which was way better than the fake queue solution.
# Todo: invalidate certificate name mismatches and self-signed certificates.
# done: prevent a domain being scanned by multiple of these scanners at the same time (pending)
# This becomes an issue when there are more scanners. And that would be depending on what type of
# scan... if a connection is made, how many and such.
# done: when are dead domains rescanned, when are they really removed from the db? never.
# done: should we set all domains entered here into pending, or only the one scanned now?
# The pending state is confusing: especially when things go wrong during a scan. So better
# ignore the pending stuff and just rescan.
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
:295  -- HTTPSConnectionPool(host='api.ssllabs.com', port=443): Max retries exceeded with url: /api/v2/analyze?host=webmail.sittard-geleen.nl&publish=off&startNew=off&fromCache=on&all=done (Caused by NewConnectionError('<requests.packages.urllib3.connection.VerifiedHTTPSConnection object at 0x1054bcc88>: Failed to establish a new connection: [Errno 60] Operation timed out',))
:296  -- Retrying 3 times, next in 20 seconds.
:294  -- something when wrong when scanning domain webmail.sittard-geleen.nl
:295  -- HTTPSConnectionPool(host='api.ssllabs.com', port=443): Max retries exceeded with url: /api/v2/analyze?host=webmail.sittard-geleen.nl&publish=off&startNew=off&fromCache=on&all=done (Caused by NewConnectionError('<requests.packages.urllib3.connection.VerifiedHTTPSConnection object at 0x1054bc9b0>: Failed to establish a new connection: [Errno 51] Network is unreachable',))
:296  -- Retrying 2 times, next in 20 seconds.
:294  -- something when wrong when scanning domain webmail.sittard-geleen.nl
:295  -- HTTPSConnectionPool(host='api.ssllabs.com', port=443): Max retries exceeded with url: /api/v2/analyze?host=webmail.sittard-geleen.nl&publish=off&startNew=off&fromCache=on&all=done (Caused by NewConnectionError('<requests.packages.urllib3.connection.VerifiedHTTPSConnection object at 0x105313908>: Failed to establish a new connection: [Errno 51] Network is unreachable',))
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
2017-09-05 15:18:58,744	DEBUG    -- scanner_tls_qualys.py:154  -- Loaded 1 domains.
2017-09-05 15:18:58,746	DEBUG    -- scanner_tls_qualys.py:333  -- Requesting cached data from qualys for webmail.sittard-geleen.nl
2017-09-05 15:19:58,681	DEBUG    -- scanner_tls_qualys.py:352  -- something when wrong when scanning domain webmail.sittard-geleen.nl
2017-09-05 15:19:58,685	DEBUG    -- scanner_tls_qualys.py:353  -- EOF occurred in violation of protocol (_ssl.c:749)
2017-09-05 15:19:58,685	DEBUG    -- scanner_tls_qualys.py:354  -- Retrying 3 times, next in 20 seconds.
2017-09-05 15:20:49,209	DEBUG    -- scanner_tls_qualys.py:352  -- something when wrong when scanning domain webmail.sittard-geleen.nl
2017-09-05 15:20:49,209	DEBUG    -- scanner_tls_qualys.py:353  -- ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response',))
2017-09-05 15:20:49,210	DEBUG    -- scanner_tls_qualys.py:354  -- Retrying 2 times, next in 20 seconds.


^CProcess ForkPoolWorker-2050:


Soms ook ZONDER enige feedback, en daar kan je dan niet veel aan doen...
Dus wat nu? Een resume optie kan erg goed helpen... want je weet niet wanneer het gebeurd.
En je kan het verder ook niet meten...

File "/usr/local/Cellar/python3/3.6.0/Frameworks/Python.framework/Versions/3.6/lib/python3.6/threading.py", line 1072, in _wait_for_tstate_lock
elif lock.acquire(block, timeout):

File "/usr/local/Cellar/python3/3.6.0/Frameworks/Python.framework/Versions/3.6/lib/python3.6/threading.py", line 1072, in _wait_for_tstate_lock
elif lock.acquire(block, timeout):

Some other nice errors:

calculating score on 2017-09-06 08:23:22.714449+00:00 for beveiligd.harlingen.nl
Traceback (most recent call last):
  File "/usr/local/lib/python3.6/site-packages/django/db/backends/base/base.py", line 211, in _commit
    return self.connection.commit()
sqlite3.OperationalError: database is locked

The above exception was the direct cause of the following exception:

Because of the development server, and using sqlite or something like that.



2017-09-06 08:2    -- scanner_tls_qualys.py:318  -- secure.zoeterwoude.nl (91.213.115.145) = T
2017-09-06 08 G    -- scanner_tls_qualys.py:396  -- Trying to save scan for secure.zoeterwoude.nl
Error callback!
get() returned more than one Endpoint -- it returned 2!
{}
2017-09
On secure.zoeterwoude.nl, webmail.zoeterwoude.nl, zoeterwoude.nl consistently. Why? During Save.
todo: when the error callback is triggered, find out what line it triggered... because debugging is
hard now.
It's a django error, using "get" getting back multiple objects. Interesting... so the database
can be poluted with multiple instead of one.
-> there are two endpoints, one is dead, one not. Both have the SAME ip. Should check for dead there?
-> or ... we can't ... i see now :) How do we deal with this?

todo: unable to resolve domain name fouten wegwerken: we bewaren het domain, wordt dan WEER gescand.
Hij moet gewoon "dood" worden gemaakt. Kunnen altijd later wel kijken of hij toch niet leeft.
- Dit kan je oplossen door alleen maar alive dingen te scannen. Het wordt wel allemaal goed uitgezet.
- we kijken nu in de scans bij het aanroepen van de scanner. de scanner zelf heeft geen oordeel over
- wat wel of niet gescanned moet worden... behalve niet "te vaak" scannen.
"""

import json
import logging
import sys
from datetime import date, datetime, timedelta
from random import randint
from time import sleep

import pytz
import requests

from failmap_admin.organizations.models import Url
from failmap_admin.scanners.models import Endpoint, TlsQualysScan, TlsQualysScratchpad


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

        ScannerTlsQualys.log = logging.getLogger('scanner_tls_qualys')
        ScannerTlsQualys.log.handlers = []  # bad workaround:
        # above workaround based on https://github.com/ipython/ipython/issues/8282
        ScannerTlsQualys.log.setLevel(logging.DEBUG)

        # http://stackoverflow.com/questions/14058453/
        # making-python-loggers-output-all-messages-to-stdout-in-addition-to-log#14058475
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter('%(asctime)s\t%(levelname)-8s -- '
                                               '%(filename)s:%(lineno)-4s -- %(message)s'))
        # lunix only solution.
        logging.addLevelName(logging.WARNING,
                             "\033[1;31m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
        logging.addLevelName(logging.ERROR,
                             "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.ERROR))

        ScannerTlsQualys.log.addHandler(console)
        ScannerTlsQualys.log.debug("Logging initialized")

    @staticmethod
    def scan(domains):
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

        for domain in domains:
            pool.apply_async(ScannerTlsQualys.scantask, [domain],
                             callback=ScannerTlsQualys.success_callback,
                             error_callback=ScannerTlsQualys.error_callback)
            # ScannerTlsQualys.scantask(domain) # old sequential approach
            sleep(50 + randint(0, 10))  # Start a new task, but don't pulsate too much.

        pool.close()
        pool.join()  # possible cause of locks, solution: set thread timeout. A scan max takes 5 min
        ScannerTlsQualys.log.debug("Done")

    @staticmethod
    def success_callback(x):
        ScannerTlsQualys.log.debug("Success!")
        print("Success!")

    @staticmethod
    def error_callback(x):
        print("Error callback!")
        print(x)
        print(vars(x))  # we're getting a statusDetails back... probably not handled by the code

    # max N at the same time? how to?
    # what happens when there is no internet?
    @staticmethod
    def scantask(domain):
        """
        Carries out a scan until the ERROR or READY is returned. There will be many checks performed
        by the scanner, signalled by TESTING_ messages. There also are many DNS messages when
        starting the scan.

        A scan usually takes about two minutes.

        :param domains:
        :return:
        """

        data = {}
        data['status'] = "NEW"

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
                if data['status'] == "ERROR":
                    ScannerTlsQualys.scratch(domain, data)  # we always want to see what happened.
                    ScannerTlsQualys.clean_endpoints(domain, [])
                    return

            else:
                data['status'] = "FAILURE"  # stay in the loop
                ScannerTlsQualys.log.debug("Unexpected result from API")
                ScannerTlsQualys.log.debug(data)  # print for debugging purposes
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
        for qualys_endpoint in data['endpoints']:
            # insert or update automatically. An endpoint is unique (protocol, port, ip, domain)
            # when an endpoint is found here, then it is obviously not dead....
            # todo: There is a failstate, where there is both an endpoint alive, and one dead
            # with the same IP and all other criteria. That should not happen.
            # get or create also doesn't really help. - dedupe endpoint function.

            # take in account there might be multiple "the same" endpoints, due to human mistakes
            # or bugs, or whatever. We're going to reduce it back to a single endpoint and continue
            # working with that. There is really no use to have multiple the same endpoints.
            # - especially since we don't store the reverse name as unique.
            # todo: ah, hier maakte hij endpoints zonder URL er aan :)
            # perhaps i have to do some fixing outside of this thing...???
            # instead of automerging behaviour?
            endpoints = Endpoint.objects.all().filter(domain=domain,
                                                      ip=qualys_endpoint['ipAddress'],
                                                      port=443,
                                                      protocol="https")

            # count here, as the number of elements is possibly modified in below process
            count = endpoints.count()

            # if there is no endpoint yet, then create it. (as with get or create
            if count == 0:
                ScannerTlsQualys.log.debug("This endpoint is new: %s %s:443" %
                                           (domain, qualys_endpoint['ipAddress']))
                # todo: find the URL that matches this ... if there is any, if not, safe it without
                # an URL... there might be reasons for scanning things without an URL object.
                # todo: url + organization are unique. Can be that mulitple organizations have
                # the same URL. So add the organization to the scanner, otherwise the below
                # association will not be OK.
                failmap_endpoint = Endpoint()
                try:
                    failmap_endpoint.url = Url.objects.filter(url=domain).first()  # todo: see above
                except:
                    # todo: make less broad exception
                    failmap_endpoint.url = ""
                failmap_endpoint.domain = domain  # not used anymore. Filled for legacy reasons.
                failmap_endpoint.port = 443
                failmap_endpoint.protocol = "https"
                failmap_endpoint.ip = qualys_endpoint['ipAddress']
                failmap_endpoint.is_dead = False
                failmap_endpoint.save()

            if count > 1:
                ScannerTlsQualys.log.debug("Multiple similar endpoints detected for %s" % domain)
                ScannerTlsQualys.log.debug("Flattening similar endpoints to a single one.")
                # uh oh, there are multiple endpoints that do the same... let's reduce it
                # to a single one.
                # first, revivive all of them, so the one we will work with has the correct state.
                for endpoint in endpoints:
                    endpoint.is_dead = False
                    endpoint.is_dead_reason = ""
                    endpoint.save()

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
                ScannerTlsQualys.log.debug("An endpoint exists and is set to be alive.")
                # just one existing endpoint. Since we got it back it's alive.
                failmap_endpoint = endpoints[0]
                failmap_endpoint.is_dead = False
                failmap_endpoint.is_dead_reason = ""
                failmap_endpoint.save()

            # todo: ah, hier maakt hij endpoints zonder URL er aan :)
            # this code was the old "get or create" approach that could not handle duplicate endpoints
            # failmap_endpoint, created = Endpoint.objects.get_or_create(
            #     domain=domain,
            #     ip=qualys_endpoint['ipAddress'],
            #     port=443,
            #     protocol="https"
            # )
            # if created:
            #     ScannerTlsQualys.log.debug("Created a new endpoint for %s and adding results",
            #                                domain)
            # else:
            #     ScannerTlsQualys.log.debug("Updating scans of existing endpoint %s",
            #                                failmap_endpoint.id)
            #     # it exists, so cannot be dead... update it to be alive (below functions don't seem
            #     # to work...
            #     failmap_endpoint.is_dead = False
            #     failmap_endpoint.is_dead_reason = ""
            #     failmap_endpoint.save()

            # possibly also record the server name, as we get it. It's not really of value.

            # get the most recent scan of this endpoint, if any and work with that to save data.
            # data is saved when the rating didn't change, otherwise a new record is created.
            scan = TlsQualysScan.objects.filter(endpoint=failmap_endpoint).\
                order_by('-scan_moment').first()

            rating = qualys_endpoint['grade'] if 'grade' in qualys_endpoint.keys() else 0
            rating_no_trust = qualys_endpoint['gradeTrustIgnored'] \
                if 'gradeTrustIgnored' in qualys_endpoint.keys() else 0

            if scan:
                ScannerTlsQualys.log.debug("There was already a scan on this endpoint.")

                if scan.qualys_rating == rating and scan.qualys_rating_no_trust == rating_no_trust:
                    ScannerTlsQualys.log.debug("Scan did not alter the rating, "
                                               "updating scan date only.")
                    scan.scan_moment = datetime.now(pytz.utc)
                    scan.scan_time = datetime.now(pytz.utc)
                    scan.scan_date = datetime.now(pytz.utc)
                    scan.save()

                else:
                    ScannerTlsQualys.log.debug("Rating changed, "
                                               "we're going to save the scan to retain history")
                    scan = TlsQualysScan()
                    scan.endpoint = failmap_endpoint
                    scan.qualys_rating = rating
                    scan.qualys_rating_no_trust = rating_no_trust
                    scan.scan_moment = datetime.now(pytz.utc)
                    scan.scan_time = datetime.now(pytz.utc)
                    scan.scan_date = datetime.now(pytz.utc)
                    scan.rating_determined_on = datetime.now(pytz.utc)
                    scan.save()

            else:
                # todo: don't like to have the same code twice.
                ScannerTlsQualys.log.debug("This endpoint was never scanned, creating a new scan.")
                scan = TlsQualysScan()
                scan.endpoint = failmap_endpoint
                scan.qualys_rating = rating
                scan.qualys_rating_no_trust = rating_no_trust
                scan.scan_moment = datetime.now(pytz.utc)
                scan.scan_time = datetime.now(pytz.utc)
                scan.scan_date = datetime.now(pytz.utc)
                scan.rating_determined_on = datetime.now(pytz.utc)
                scan.save()

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
            killable_endpoint.is_dead = 1
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

        # the reverse is not always true: while you can genericly revive domains if there is a
        # working endpoint. This scanner can not kill the domain if there is no TLS.
        # However, you can IF there are no other endpoints and there is no TLS endpoint.
        # after scanning a few times. ... There are a few domains in limbo: those who have
        # no endpoints, that have been scanned, but may be visited by other scanners...
        # This scanner doesn't check if the domain is dead (or exists at al) the benefit is that
        # you can still re-check a domain by scanning it. So make sure the list of domains to be
        # scanned is good enough... So let's kill some urls...

        # if an url has NO endpoints,
