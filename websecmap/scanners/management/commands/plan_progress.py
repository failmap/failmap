import logging
from pprint import pprint

from django.core.management.base import BaseCommand

from websecmap.scanners import plannedscan

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Normally all scans are planned and executed using periodic tasks. This command however will plan
    all verify, discovery and scan tasks on the entire system.
    """

    def handle(self, *args, **options):
        pprint(plannedscan.progress())
