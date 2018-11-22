import logging

from failmap.app.management.commands._private import ScannerTaskCommand
from failmap.scanners.scanner import (debug, dnssec, dummy, ftp, http, mail, onboard, plain_http,
                                      screenshot, security_headers, tls_osaft, tls_qualys)

log = logging.getLogger(__name__)


class Command(ScannerTaskCommand):
    """ Can perform a host of scans. Run like: failmap scan [scanner_name] and then options."""

    help = __doc__

    scanners = {
        'dnssec': dnssec,
        'headers': security_headers,
        'plain': plain_http,
        'endpoints': http,
        'tls': tls_osaft,
        'tlsq': tls_qualys,
        'ftp': ftp,
        'screenshot': screenshot,
        'onboard': onboard,
        'dummy': dummy,
        'debug': debug,
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
