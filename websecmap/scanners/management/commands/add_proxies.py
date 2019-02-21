import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.models import ScanProxy

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Adds a list of IP addresses to the scanproxy list."""

    def add_arguments(self, parser):
        parser.add_argument('ips', nargs='*', help='List of IP adresses')
        super().add_arguments(parser)

    def handle(self, *args, **options):

        for ip in options['ips']:
            ScanProxy.add_address(ip)
