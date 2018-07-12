import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Determine if there are major differences between Qualys and O-Saft scanner'

    def handle(self, *args, **options):
        from failmap.scanners.scanner_tls_osaft import compare_results
        compare_results()
