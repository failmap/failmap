import logging
from datetime import datetime

import pytz
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.map.determineratings import DetermineRatings
from failmap_admin.organizations.models import Organization, Url
from failmap_admin.scanners.scanner_dns import ScannerDns
from failmap_admin.scanners.state_manager import StateManager
from failmap_admin.scanners.scanner_security_headers import ScannerSecurityHeaders

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Development command'

    def handle(self, *args, **options):
        Command.develop_determineratings()

    @staticmethod
    def develop_security_headers_scanner():
        s = ScannerSecurityHeaders()
        u = Url.objects.all().filter(url='zoeken.haarlemmermeer.nl').get()
        u = Url.objects.all().filter(url='www.ibdgemeenten.nl').get()
        s.scan_headers(u)


    @staticmethod
    def develop_determineratings():
        # DetermineRatings.default_ratings()
        # return

        # DetermineRatings.significant_times(organization=organization)
        # urls = Url.objects.all().filter(organization=organization)
        # for url in urls:
        #     DetermineRatings.get_url_score_modular(url)

        when = datetime(2016, 12, 31, 0, 0, tzinfo=pytz.utc)
        # when = datetime.now(pytz.utc)

        organization = Organization.objects.filter(name="Arnhem").get()
        DetermineRatings.clear_organization_and_urls(organization)
        DetermineRatings.rate_organization_urls_efficient(organization, create_history=True)
        # ratings are always different since we now also save last scan date.
        # only creates things for near midnight. Should check if today, and then save for now.
        DetermineRatings.rate_organization_efficient(organization, create_history=True)
        # create one for NOW, not this night. This is a bug :)
        DetermineRatings.rate_organization_efficient(organization)
