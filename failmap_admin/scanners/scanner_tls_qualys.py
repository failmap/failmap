# References:
# https://github.com/ssllabs/ssllabs-scan/blob/stable/ssllabs-api-docs.md

# Todo: use celery for distributed scanning, multiple threads. (within reason)
# Can be a max of N threads? :)
# Todo: invalidate certificate name mismatches and self-signed certificates.
# todo: prevent a domain being scanned by multiple of these scanners at the same time (pending)
# todo: when are dead domains rescanned, when are they really removed from the db? that's for all
# todo: should we set all domains entered here into pending, or only the one scanned now?
# todo: check for network availability.
# todo: this can be done distributed, using a different approach.

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


"""
    Selery tasks:

    A thing for allowing an X number of scans at the same time.
        Would do that for _all_ of these instances. So it is sort of managing a flock/fleet.
        It would be simple and have a max number of scanners. This has to be calculated.

    A thing for scanning a domain and getting back info on ERROR or READY and waiting otherwise.

    A thing to do administration of the tasks.
        And how does it "pend" things?

    A set of testcases that tests the coherence between these things.
    Another, new, way of testing...
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

        self.log = logging.getLogger('scanner_tls_qualys')
        self.log.handlers = []  # bad workaround: https://github.com/ipython/ipython/issues/8282
        self.log.setLevel(logging.DEBUG)

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

        self.log.addHandler(console)
        self.log.debug("Logging initialized")

    def scan(self, domains):
        """
        Qualys stores results in their cache as long as there is space.
        We assume that this lasts about 30 minutes, which is usually the case.

        A scan of a domain might take over ten minutes, depending on how busy qualys is.
        If there is no answer yet from a scan, just retry after a series of other domains
        have been tested. To make sure that there is about-enough time in between, we're testing
        domains per 20. So 3 passes times 20 domains should result in some meaningful output.

        If you're too fast, you'll get "Too many new assessments too fast. Please slow down."

        In case of a cache-miss qualys will restart a scan. Don't wait too long between scans.

        :param domains:
        :return:
        """

        domains = self.external_service_task_rate_limit(domains)

        self.log.debug("Loaded %s domains.", len(domains))

        sq = ScanQueue(domains)
        sq.debug()

        while sq.has_items():
            domain = sq.get_next()
            self.log.debug("Attempt scanning domain %s ", domain)

            if self.endpoints_alive_in_past_24_hours(domain):
                sq.remove(domain)
                continue

            if self.rate_limit:
                # wait 25 seconds + 0-9 random seconds, wait longer with fewer domains
                sleep(25 + randint(0, 9) + (300 / sq.length()))  # don't pulsate.

            data = self.service_provider_scan_via_api(domain)
            self.scratch(domain, data)  # for debugging
            self.report_to_console(domain, data)  # for more debugging

            if data['status'] == "READY" and 'endpoints' in data.keys():
                sq.remove(domain)
                self.save_scan(domain, data)
                self.clean_endpoints(domain, data['endpoints'])

            # in nearly all cases the domain could not be retrieved, so clean the endpoints
            # and move on.
            if data['status'] == "ERROR":
                self.clean_endpoints(domain, [])

    def external_service_task_rate_limit(self, domains):
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
            if not self.endpoints_alive_in_past_24_hours(domain):
                domains_to_scan.append(domain)

        # prevent duplicates
        domains_to_scan = set(domains_to_scan)
        return list(domains_to_scan)

    def report_to_console(self, domain, data):
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
                self.log.debug("%s (%s) = %s" %
                               (domain, endpoint['ipAddress'], endpoint['grade'])) \
                    if 'grade' in endpoint.keys() else self.log.debug("%s = No TLS (0)" % domain)

        if data['status'] == "ERROR":
            self.log.debug("ERROR: Got message: %s", data['statusMessage'])

        if data['status'] == "DNS":
            self.log.debug("DNS: Got message: %s", data['statusMessage'])

        if data['status'] == "IN_PROGRESS":
            for endpoint in data['endpoints']:
                self.log.debug("Domain %s in progress. Endpoint: %s. Message: %s "
                               % (domain, endpoint['ipAddress'], endpoint['statusDetails']))

    # publish: off, it's friendlier to the domains scanned
    # startnew: off, that's done automatically when needed by service provider
    # fromcache: on: they are chached for a few hours only.
    def service_provider_scan_via_api(self, domain):
        self.log.debug("Requesting cached data from qualys for %s", domain)
        payload = {'host': domain, 'publish': "off", 'startNew': "off",
                   'fromCache': "on", 'all': "done"}

        try:
            response = requests.get("https://api.ssllabs.com/api/v2/analyze", params=payload)
            return response.json()
        except requests.RequestException as e:
            # todo: auto-retry after x time. By Celery.
            self.log.debug("something when wrong when scanning domain %s", domain)
            self.log.debug(e)

    # todo: django.db.utils.IntegrityError: NOT NULL constraint failed: .endpoint_id
    def save_scan(self, domain, data):
        """
        Saves another scan to the database. Does some endpoint plumbing.
        :param domain:
        :param data: raw JSON data from qualys
        :return:
        """
        self.log.debug("Trying to save scan for %s", domain)

        # manage endpoints
        for qualys_endpoint in data['endpoints']:
            # insert or update automatically. An endpoint is unique (protocol, port, ip, domain)

            failmap_endpoint, created = Endpoint.objects.get_or_create(
                domain=domain,
                ip=qualys_endpoint['ipAddress'],
                port=443,
                protocol="https"
            )
            if created:
                self.log.debug("Created a new endpoint for %s and adding results", domain)
            else:
                self.log.debug("Updating scans of existing endpoint %s", failmap_endpoint.id)

            # possibly also record the server name, as we get it. It's not really of value.

            # get the most recent scan of this endpoint, if any and work with that to save data.
            # data is saved when the rating didn't change, otherwise a new record is created.
            scan = TlsQualysScan.objects.filter(endpoint=failmap_endpoint).\
                order_by('-scan_moment').first()

            rating = qualys_endpoint['grade'] if 'grade' in qualys_endpoint.keys() else 0
            rating_no_trust = qualys_endpoint['gradeTrustIgnored'] \
                if 'gradeTrustIgnored' in qualys_endpoint.keys() else 0

            if scan:
                self.log.debug("There was already a scan on this endpoint.")

                if scan.qualys_rating == rating and scan.qualys_rating_no_trust == rating_no_trust:
                    self.log.debug("Scan did not alter the rating, updating scan_date only.")
                    scan.scan_moment = datetime.now(pytz.utc)
                    scan.scan_time = datetime.now(pytz.utc)
                    scan.scan_date = datetime.now(pytz.utc)
                    scan.save()

                else:
                    self.log.debug("Rating changed, we're going to save the scan to retain history")
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
                self.log.debug("This endpoint was never scanned, creating a new scan.")
                scan = TlsQualysScan()
                scan.endpoint = failmap_endpoint
                scan.qualys_rating = rating
                scan.qualys_rating_no_trust = rating_no_trust
                scan.scan_moment = datetime.now(pytz.utc)
                scan.scan_time = datetime.now(pytz.utc)
                scan.scan_date = datetime.now(pytz.utc)
                scan.rating_determined_on = datetime.now(pytz.utc)
                scan.save()

    def scratch(self, domain, data):
        self.log.debug("Scratching data for %s", domain)
        scratch = TlsQualysScratchpad()
        scratch.domain = domain
        scratch.data = json.dumps(data)
        scratch.save()

    # smart rate limiting
    def endpoints_alive_in_past_24_hours(self, domain):
        x = TlsQualysScan.objects.filter(endpoint__domain=domain,
                                         endpoint__port=443,
                                         endpoint__protocol__in=["https"],
                                         scan_date__gt=date.today() - timedelta(1)).exists()
        if x:
            self.log.debug("domain %s was scanned in past 24 hours", domain)
        else:
            self.log.debug("domain %s was NOT scanned in past 24 hours", domain)
        return x

    def clean_endpoints(self, domain, endpoints):
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
        self.log.debug("Cleaning endpoints for %s", domain)

        # list of addresses that we're NOT going to declare dead :)
        ip_addresses = []
        for endpoint in endpoints:
            ip_addresses.append(endpoint['ipAddress'])

        e = Endpoint
        e.objects.filter(is_dead=0, domain=domain, port=443, protocol="https")
        killable_endpoints = e.objects.exclude(ip__in=ip_addresses)

        for killable_endpoint in killable_endpoints:
            self.log.debug('Found an endpoint that can get killed: %s', killable_endpoint.domain)
            killable_endpoint.is_dead = 1
            killable_endpoint.is_dead_since = datetime.now(pytz.utc)
            killable_endpoint.is_dead_reason = "Endpoint not found anymore in qualys scan."
            killable_endpoint.save()

        self.revive_url_with_alive_endpoints(domain)

    def revive_url_with_alive_endpoints(self, domain):
        """
        A generic method that revives domains that have endpoints that are not dead.

        The domain is then revived by force.

        :return:
        """
        self.log.debug("Genericly attempting to revive url using endpoints from %s", domain)

        # if there is an endpoint that is alive, make sure that the domain is set to alive
        # this should be a task of more generic endpoint management
        if TlsQualysScan.objects.filter(endpoint__is_dead=0, endpoint__domain=domain).exists():
            urls = Url.objects.filter(url=domain, isdead=True)

            for url in urls:
                url.isdead = False
                url.isdeadsince = datetime.now(pytz.utc)
                url.isdeadreason = "There are endpoints discovered via scanner tls qualys"
                url.save()  # might be empty, which is fine...


class ScanQueue:
    """
    A supporting class that has some semantic features to make the above code easier to understand

    This class does the logic in what order to scan domains.
    """
    queue = []

    def get_next(self):
        return self.queue.pop()

    # http://stackoverflow.com/questions/9671224/
    # these control-loops might be outsourced to class, so you have while(domain=x.next()):
    # it will save 3 nests and add some complexity.
    def __init__(self, domains):

        chunks = [domains[x:x + 20] for x in range(0, len(domains), 20)]
        for chunk in chunks:

            # do three passes, as described above
            attempt = 0
            while attempt < 3:
                for domain in chunk:
                    print("Adding " + domain + " to the queue")
                    self.queue.append(domain)
                attempt += 1

    def remove(self, domain):
        print("Removing " + domain + " from the queue")
        while domain in self.queue:
            self.queue.remove(domain)  # remove all

    def has_items(self):
        return len(self.queue)

    def length(self):
        return len(self.queue)

    def debug(self):
        print("There are " + str(len(self.queue)) + " items in the queue. ")
