import logging

from websecmap.app.management.commands._private import GenericTaskCommand
from websecmap.map import prepare_caches

log = logging.getLogger(__name__)


class Command(GenericTaskCommand):
    """Prepare caches after running report."""

    help = __doc__

    def handle(self, *args, **options):
        try:
            self.scanner_module = prepare_caches
            super().handle(self, *args, **options)
        except KeyboardInterrupt:
            log.info("Received keyboard interrupt. Stopped.")
