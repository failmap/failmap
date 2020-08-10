import logging
from pprint import pprint

from django.core.management.base import BaseCommand

from websecmap.map.report import PUBLISHED_SCAN_TYPES
from websecmap.scanners import plannedscan

log = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        pprint(plannedscan.plan_outdated_scans(PUBLISHED_SCAN_TYPES))
