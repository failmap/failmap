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

import json
import logging
import sys
from datetime import date, datetime, timedelta
from random import randint
from time import sleep
import os
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
        ScannerTlsQualys.log.handlers = []  # bad workaround: https://github.com/ipython/ipython/issues/8282
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
        pool = Pool(processes=25)  # max 25 at the same time...

        domains = ScannerTlsQualys.external_service_task_rate_limit(domains)
        ScannerTlsQualys.log.debug("Loaded %s domains.", len(domains))

        # if you want to run this from multiple domains, you'd need celery still.
        # which we now can upgrade to.
        # with 30 seconds per domain, you can only scan 2800 domains a day...
        # todo: check X-Max-Assessments and X-Current-Assessments headers.
        # ('x-clientmaxassessments', ('X-ClientMaxAssessments', '25')),
        # ('x-max-assessments', ('X-Max-Assessments', '25')),
        # you can do 25 at the same time? wtf. If each takes two minutes (120 seconds).
        # you can scan about every 4.8 seconds. So let's be nice and start every 10 seconds.
        # that we we can do 8400 domains a day, which is awesome.
        # we take it a bit slower, since perhaps there might be a manual scan or two to run.
        # what happens if you run too many scans at the same time... well... don't know :)

        for domain in domains:
            asd = pool.apply_async(ScannerTlsQualys.scantask, [domain], callback=ScannerTlsQualys.success_callback, error_callback=ScannerTlsQualys.error_callback)
            # ScannerTlsQualys.scantask(domain) # this task should be running independently?
            sleep(10 + randint(0, 9))  # Start a new task, but don't pulsate too much.

        pool.close()
        pool.join()
        ScannerTlsQualys.log.debug("Done")

    @staticmethod
    def success_callback(x):
        print("Success!")

    @staticmethod
    def error_callback(x):
        print("Error callback!")
        print(vars(x))  # we're getting a statusDetails back...

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

            if data['status'] == "READY" and 'endpoints' in data.keys():
                ScannerTlsQualys.save_scan(domain, data)
                ScannerTlsQualys.clean_endpoints(domain, data['endpoints'])
                return

            # in nearly all cases the domain could not be retrieved, so clean the endpoints
            # and move on. As the result was "error", over internet, you should not need to check
            # if there is an internet connection... obviously
            if data['status'] == "ERROR":
                ScannerTlsQualys.clean_endpoints(domain, [])
                return

            # to save time the "ready" and "error" state are already checked above.
            # because why wait when we have a result already.
            # https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md
            # advice is 10 seconds... well... doesn't really matter
            sleep(30 + randint(0, 9))  # don't pulsate.

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

        if data['status'] == "READY":
            for endpoint in data['endpoints']:
                ScannerTlsQualys.log.debug("%s (%s) = %s" %
                               (domain, endpoint['ipAddress'], endpoint['grade'])) \
                    if 'grade' in endpoint.keys() else ScannerTlsQualys.log.debug("%s = No TLS (0)" % domain)

        if data['status'] == "ERROR":
            ScannerTlsQualys.log.debug("ERROR: Got message: %s", data['statusMessage'])

        if data['status'] == "DNS":
            ScannerTlsQualys.log.debug("DNS: Got message: %s", data['statusMessage'])

        if data['status'] == "IN_PROGRESS":
            for endpoint in data['endpoints']:
                ScannerTlsQualys.log.debug("Domain %s in progress. Endpoint: %s. Message: %s "
                               % (domain, endpoint['ipAddress'], endpoint['statusDetails']))

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

        try:
            response = requests.get("https://api.ssllabs.com/api/v2/analyze", params=payload)
            # print(vars(response.headers))
            return response.json()
        except requests.RequestException as e:
            # todo: auto-retry after x time. By Celery.
            ScannerTlsQualys.log.debug("something when wrong when scanning domain %s", domain)
            ScannerTlsQualys.log.debug(e)

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
            failmap_endpoint, created = Endpoint.objects.get_or_create(
                domain=domain,
                ip=qualys_endpoint['ipAddress'],
                port=443,
                protocol="https"
            )
            if created:
                ScannerTlsQualys.log.debug("Created a new endpoint for %s and adding results", domain)
            else:
                ScannerTlsQualys.log.debug("Updating scans of existing endpoint %s", failmap_endpoint.id)
                # it exists, so cannot be dead... update it to be alive (below functions don't seem
                # to work...
                failmap_endpoint.is_dead = False
                failmap_endpoint.is_dead_reason = ""
                failmap_endpoint.save()

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
                    ScannerTlsQualys.log.debug("Scan did not alter the rating, updating scan_date only.")
                    scan.scan_moment = datetime.now(pytz.utc)
                    scan.scan_time = datetime.now(pytz.utc)
                    scan.scan_date = datetime.now(pytz.utc)
                    scan.save()

                else:
                    ScannerTlsQualys.log.debug("Rating changed, we're going to save the scan to retain history")
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
            ScannerTlsQualys.log.debug('Found an endpoint that can get killed: %s', killable_endpoint.domain)
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
        ScannerTlsQualys.log.debug("Genericly attempting to revive url using endpoints from %s", domain)

        # if there is an endpoint that is alive, make sure that the domain is set to alive
        # this should be a task of more generic endpoint management
        if TlsQualysScan.objects.filter(endpoint__is_dead=0, endpoint__domain=domain).exists():
            urls = Url.objects.filter(url=domain, is_dead=True)

            for url in urls:
                url.is_dead = False
                url.is_deadsince = datetime.now(pytz.utc)
                url.is_dead_reason = "There are endpoints discovered via scanner tls qualys"
                url.save()  # might be empty, which is fine...
