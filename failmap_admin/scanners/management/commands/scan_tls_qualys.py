import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.map.determineratings import DetermineRatings
from failmap_admin.scanners.managers import StateManager
from failmap_admin.scanners.models import Url
from failmap_admin.scanners.scanner_tls_qualys import ScannerTlsQualys, TlsQualysScratchpad

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Perform scans, start somewhere and just go!'

    # https://docs.djangoproject.com/en/1.11/howto/custom-management-commands/
    # def add_arguments(self, parser):
    #    parser.add_argument('poll_id', nargs='+', type=int)

    do_scan = True
    do_rate = True

    def handle(self, *args, **options):
        while 1:
            self.scan()

    def scan(self):
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
            Command.scan_new_urls()  # always try to scan new urls first, regardless of organization
            Command.scan_organization(organization)

    @staticmethod
    def scan_organization(organization):
        """

        :return: list of url objects
        """
        # This scanner only scans urls with endpoints (because we inner join endpoint_is_dead)

        # Using the HTTP scanner, it's very easy and quick to see if a url resolves.
        # This is much faster than waiting 1.5 minutes for qualys to figure it out.
        # So we're only scanning what we know works.
        logger.info("Scanning organization: %s" % organization)

        urls = Url.objects.filter(organization=organization,
                                  is_dead=False,
                                  not_resolvable=False,
                                  endpoint__is_dead=False,
                                  endpoint__protocol="https",
                                  endpoint__port=443)

        if not urls:
            logger.info("There are no alive https urls for this organization: %s" % organization)
            return

        s = ScannerTlsQualys()
        s.scan([url.url for url in urls])

        dr = DetermineRatings()
        for url in urls:
            dr.rate_url(url=url)
        dr.rate_organization(organization=organization)

    @staticmethod
    def scan_new_urls():
        # find urls that don't have an qualys scan and are resolvable on https/443
        urls = Url.objects.filter(is_dead=False,
                                  not_resolvable=False,
                                  endpoint__port=443,
                                  ).exclude(endpoint__tlsqualysscan__isnull=False)

        logger.info("Good news! There are %s urls to scan!" % urls.count())

        logger.debug("These are the new urls:")
        for url in urls:
            logger.debug(url)

        s = ScannerTlsQualys()
        dr = DetermineRatings()
        for url in urls:
            s.scan([url.url])  # Scan here, speed up results on map.
            dr.rate_url(url=url)
            dr.rate_organization(organization=url.organization)

        return urls
