import logging
from pprint import pprint

from django.core.management.base import BaseCommand

from websecmap.scanners.scanner.resolve_ip import refresh_ips

log = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        pprint(refresh_ips())
