import logging

from failmap.app.management.commands._private import ScannerTaskCommand
from failmap.scanners import scanner_http

log = logging.getLogger(__name__)


class Command(ScannerTaskCommand):
    """Perform plain http scan on selected organizations."""

    help = __doc__

    scanner_module = scanner_http
