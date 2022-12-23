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
    bannergrab_nmap,
)

log = logging.getLogger(__name__)

scanners = {
    "onboard": onboard,
    "dummy": dummy,
    "dnssec": dnssec,
    "security_headers": security_headers,
    "plain_http": plain_http,
    "tls_qualys": tls_qualys,
    "ftp": ftp,
    "internet_nl_v2_mail": internet_nl_v2_mail,
    "screenshot": screenshot,
    "internet_nl_v2_web": internet_nl_v2_web,
    "dns_clean_wildcards": dns_clean_wildcards,
    "bannergrab_nmap": bannergrab_nmap,
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
                print(f"Scanner does not exist. Please specify a scanner: {scanners.keys()} ")
                return

            self.scanner_module = scanners[options["scanner"][0]]
            return super().handle(self, *args, **options)

        except KeyboardInterrupt:
            log.info("Received keyboard interrupt. Stopped.")
