import logging

from websecmap.app.management.commands._private import GenericTaskCommand
from websecmap.pro import urllist_report_historically

log = logging.getLogger(__name__)


class Command(GenericTaskCommand):
    """Rebuild url ratings (fast) and add a report for today if things changed. Creates stats for two days."""

    help = __doc__

    def handle(self, *args, **options):

        try:
            self.scanner_module = urllist_report_historically
            return super().handle(self, *args, **options)
        except KeyboardInterrupt:
            log.info("Received keyboard interrupt. Stopped.")
