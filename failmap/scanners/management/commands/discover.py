import logging

from failmap.app.management.commands._private import DiscoverTaskCommand
from failmap.scanners.scanner import dns, dns_known_subdomains, ftp, http, mail

log = logging.getLogger(__name__)


class Command(DiscoverTaskCommand):
    """Can perform a host of scans. Run like: failmap scan [scanner_name] and then options."""

    help = __doc__

    # todo: subdomains, from scanner.dns
    scanners = {
        'ftp': ftp,
        'http': http,
        'subdomains': dns,
        'known_subdomains': dns_known_subdomains,
        'mail': mail
    }

    def add_arguments(self, parser):
        parser.add_argument('scanner', nargs=1, help='The scanner you want to use.', choices=self.scanners)
        super().add_arguments(parser)

    def handle(self, *args, **options):

        try:
            if options['scanner'][0] not in self.scanners:
                print("Scanner does not exist. Please specify a scanner: %s " % self.scanners.keys())
                return

            self.scanner_module = self.scanners[options['scanner'][0]]
            return super().handle(self, *args, **options)

        except KeyboardInterrupt:
            log.info("Received keyboard interrupt. Stopped.")
