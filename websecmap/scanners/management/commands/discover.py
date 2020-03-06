import logging

from websecmap.app.management.commands._private import DiscoverTaskCommand
from websecmap.scanners.scanner import dns_endpoints, dns_known_subdomains, ftp, http, subdomains, dns_wildcards

log = logging.getLogger(__name__)


scanners = {
    'ftp': ftp,
    'http': http,
    'subdomains': subdomains,
    'known_subdomains': dns_known_subdomains,
    'dns_endpoints': dns_endpoints,
    'wildcards': dns_wildcards,
}


class Command(DiscoverTaskCommand):
    """Can perform a host of scans. Run like: failmap scan [scanner_name] and then options."""

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
