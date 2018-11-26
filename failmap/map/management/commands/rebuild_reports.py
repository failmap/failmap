import logging

from failmap.app.management.commands._private import ScannerTaskCommand
from failmap.map import rebuild_report

log = logging.getLogger(__name__)


class Command(ScannerTaskCommand):
    """Remove all organization and url ratings, then rebuild them from scratch. Used whan ratings changed and impact
    history. Also creates stats for over a year."""

    help = __doc__

    def handle(self, *args, **options):

        try:
            self.scanner_module = rebuild_report
            return super().handle(self, *args, **options)
        except KeyboardInterrupt:
            log.info("Received keyboard interrupt. Stopped.")
