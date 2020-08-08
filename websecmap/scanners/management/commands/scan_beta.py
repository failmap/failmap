import logging

from websecmap.app.management.commands._private import GenericTaskCommand
from websecmap.scanners.scanner_beta import debug, tls_osaft

log = logging.getLogger(__name__)

scanners = {
    'tls': tls_osaft,
    'debug': debug
}


class Command(GenericTaskCommand):
    """*BETA* Can perform a host of scans. Run like: failmap scan [scanner_name] and then options."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('scanner', nargs=1, help='The scanner you want to use.', choices=scanners)
        super().add_arguments(parser)

    def handle(self, *args, **options):

        try:
            if options['scanner'][0] not in scanners:
                print("Scanner does not exist. Please specify a scanner: %s " % scanners.keys())
                return

            self.scanner_module = scanners[options['scanner'][0]]
            return super().handle(self, *args, **options)

        except KeyboardInterrupt:
            log.info("Received keyboard interrupt. Stopped.")
