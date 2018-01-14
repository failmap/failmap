import logging

from failmap.app.management.commands._private import ScannerTaskCommand
from failmap.scanners import scanner_tls_qualys

log = logging.getLogger(__name__)


class Command(ScannerTaskCommand):
    """Demostrative NOOP scanner for example purposes."""

    help = __doc__

    scanner_module = scanner_tls_qualys
