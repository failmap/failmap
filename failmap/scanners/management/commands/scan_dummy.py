import logging

from failmap.app.management.commands._private import DramaScannerTaskCommand
from failmap.scanners import scanner_dummy

log = logging.getLogger(__name__)


class Command(DramaScannerTaskCommand):
    """Demostrative NOOP scanner for example purposes."""

    help = __doc__

    scanner_module = scanner_dummy
