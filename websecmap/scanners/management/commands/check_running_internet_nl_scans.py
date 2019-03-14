import logging

from websecmap.app.management.commands._private import DiscoverTaskCommand
from websecmap.scanners.scanner import mail

log = logging.getLogger(__name__)


class Command(DiscoverTaskCommand):
    """Checks running internet nl scans."""

    help = __doc__

    def handle(self, *args, **options):
        mail.check_running_scans()
