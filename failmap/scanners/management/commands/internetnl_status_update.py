import logging

from django.core.management.base import BaseCommand

from failmap.scanners.scanner.mail import check_running_scans

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """See if there are updates on the scans at internet.nl"""

    help = __doc__

    def handle(self, *args, **options):
        log.info("Checking status of scans on internet.nl")
        check_running_scans()
        log.info("Done checking status on internet.nl")
