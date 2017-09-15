from django.core.management.base import BaseCommand

from failmap_admin.scanners.scanner_dns import ScannerDns


class Command(BaseCommand):
    help = 'Development command'

    def handle(self, *args, **options):
        s = ScannerDns()
        s.make_wordlist()
        s.dnsrecon_brute('rotterdam.nl')
