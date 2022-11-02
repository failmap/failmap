import logging
from pprint import pprint

from django.core.management.base import BaseCommand

from websecmap.scanners import plannedscan
from websecmap.scanners.scanmetadata import get_backend_scanmetadata

log = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        metadata = get_backend_scanmetadata()
        pprint(plannedscan.plan_outdated_scans(metadata["published_scan_types"]))
