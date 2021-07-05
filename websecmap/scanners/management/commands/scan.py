import logging

from websecmap.app.management.commands._private import ScannerTaskCommand
from websecmap.scanners.scanner import (
    dns_clean_wildcards,
    dnssec,
    dummy,
    ftp,
    internet_nl_v2_mail,
    internet_nl_v2_web,
    onboard,
    plain_http,
    screenshot,
    security_headers,
    tls_qualys,
)

log = logging.getLogger(__name__)

scanners = {
    "onboard": onboard,
    "dummy": dummy,
    "dnssec": dnssec,
    "headers": security_headers,
    "plain": plain_http,
    "tlsq": tls_qualys,
    "ftp": ftp,
    "mail": internet_nl_v2_mail,
    "screenshot": screenshot,
    "internet_nl_web_v2": internet_nl_v2_web,
    "clean_wildcards": dns_clean_wildcards,
}


class Command(ScannerTaskCommand):
    """Can perform a host of scans. Run like: failmap scan [scanner_name] and then options."""

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("scanner", nargs=1, help="The scanner you want to use.", choices=scanners)
        super().add_arguments(parser)

    def handle(self, *args, **options):

        try:
            if options["scanner"][0] not in scanners:
                print("Scanner does not exist. Please specify a scanner: %s " % scanners.keys())
                return

            self.scanner_module = scanners[options["scanner"][0]]
            return super().handle(self, *args, **options)

        except KeyboardInterrupt:
            log.info("Received keyboard interrupt. Stopped.")
