import logging

from failmap.app.management.commands._private import ScannerTaskCommand
from failmap.scanners import (scanner_dnssec, scanner_dummy, scanner_ftp, scanner_http,
                              scanner_plain_http, scanner_screenshot, scanner_security_headers,
                              scanner_tls_osaft, scanner_tls_qualys)

log = logging.getLogger(__name__)


class Command(ScannerTaskCommand):
    """Can perform a host of scans. Run like: failmap scan [scanner_name] and then options."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('scanner', nargs=1, help='The scanner you want to use.')
        super().add_arguments(parser)

    def handle(self, *args, **options):

        scanners = {
            'dnssec': scanner_dnssec,
            'headers': scanner_security_headers,
            'plain': scanner_plain_http,
            'endpoints': scanner_http,
            'tls': scanner_tls_osaft,
            'tlsq': scanner_tls_qualys,
            'ftp': scanner_ftp,
            'screenshot': scanner_screenshot,
            'dummpy': scanner_dummy
        }

        if options['scanner'][0] not in scanners:
            print("Scanner does not exist. Please specify a scanner: %s " % scanners.keys())
            return

        self.scanner_module = scanners[options['scanner'][0]]
        super().handle(self, *args, **options)
