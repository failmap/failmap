import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand
from failmap_admin.map.determineratings import DetermineRatings
from failmap_admin.organizations.models import Organization, Url
from datetime import datetime
import pytz
from failmap_admin.scanners.managers import StateManager
from failmap_admin.scanners.scanner_dns import ScannerDns

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Development command'

    def handle(self, *args, **options):
        organization = Organization.objects.filter(name="Lochem").get()
        # DetermineRatings.significant_times(organization=organization)
        # urls = Url.objects.all().filter(organization=organization)
        # for url in urls:
        #     DetermineRatings.get_url_score_modular(url)
        when = datetime(2016, 12, 31, 0, 0, tzinfo=pytz.utc)
        # when = datetime.now(pytz.utc)

        DetermineRatings.rate_organization(organization=organization, when=when)