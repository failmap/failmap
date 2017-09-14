from django.core.management.base import BaseCommand

from failmap_admin.scanners.scanner_http import ScannerHttp


# todo: when tls scanner ends, it hangs.
# todo: add command line arguments: port and protocol.
class Command(BaseCommand):
    help = 'Discover http sites'

    def handle(self, *args, **options):
        s = ScannerHttp()
        s.scan_multithreaded(port=8443, protocol="https")
