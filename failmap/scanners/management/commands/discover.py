import logging

from failmap.app.management.commands._private import DiscoverTaskCommand
from failmap.scanners import scanner_ftp

log = logging.getLogger(__name__)


class Command(DiscoverTaskCommand):
    """Can perform a host of scans. Run like: failmap scan [scanner_name] and then options."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('scanner', nargs=1, help='The scanner you want to use.')
        super().add_arguments(parser)

    def handle(self, *args, **options):

        scanners = {
            'ftp': scanner_ftp
        }

        if options['scanner'][0] not in scanners:
            print("Scanner does not exist. Please specify a scanner: %s " % scanners.keys())
            return

        self.scanner_module = scanners[options['scanner'][0]]
        super().handle(self, *args, **options)
