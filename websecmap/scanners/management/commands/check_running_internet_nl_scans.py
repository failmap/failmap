import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.scanner.internet_nl_v2_websecmap import check_running_internet_nl_scans

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Checks running internet nl scans."""

    help = __doc__

    def handle(self, *args, **options):
        # This will create a bunch of tasks which need to be performed.
        tasks = check_running_internet_nl_scans()
        tasks.apply_async()
