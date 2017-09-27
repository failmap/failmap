import logging
from datetime import datetime

import pytz
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.map.determineratings import DetermineRatings
from failmap_admin.organizations.models import Organization, Url
from failmap_admin.scanners.managers import StateManager
from failmap_admin.scanners.scanner_dns import ScannerDns

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Development command'

    def handle(self, *args, **options):
        # DetermineRatings.default_ratings()
        # return

        # DetermineRatings.significant_times(organization=organization)
        # urls = Url.objects.all().filter(organization=organization)
        # for url in urls:
        #     DetermineRatings.get_url_score_modular(url)
        when = datetime(2016, 12, 31, 0, 0, tzinfo=pytz.utc)
        # when = datetime.now(pytz.utc)

        organization = Organization.objects.filter(name="Enschede").get()
        DetermineRatings.clear_organization_and_urls(organization)
        DetermineRatings.rate_organization_urls_efficient(organization, create_history=True)
        DetermineRatings.rate_organization_efficient(organization, create_history=True)
