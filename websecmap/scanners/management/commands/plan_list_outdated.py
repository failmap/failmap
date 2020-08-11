import logging

from django.core.management.base import BaseCommand

from websecmap.scanners import plannedscan

log = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        plannedscan.websecmap_list_outdated()
