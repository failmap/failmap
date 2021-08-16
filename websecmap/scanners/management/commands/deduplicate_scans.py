import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.duplicates import deduplicate_all_scans_sequentially

log = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        deduplicate_all_scans_sequentially()
