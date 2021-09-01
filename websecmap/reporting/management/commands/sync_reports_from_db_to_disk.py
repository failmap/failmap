import logging

from django.core.management.base import BaseCommand

from websecmap.reporting.diskreport import sync_reports_from_db_to_disk

log = logging.getLogger(__package__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        sync_reports_from_db_to_disk()
