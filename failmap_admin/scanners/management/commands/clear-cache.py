import logging
from datetime import datetime

import pytz
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.map.determineratings import DetermineRatings
from failmap_admin.organizations.models import Organization, Url
from failmap_admin.scanners.scanner_dns import ScannerDns
from failmap_admin.scanners.state_manager import StateManager

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Clear all caches'

    def handle(self, *args, **options):
        logger.warning('This does not clear your browsers chache. For JSON this might be relevant.')
        cache.clear()
