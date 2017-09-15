from django.core.management.base import BaseCommand

from failmap_admin.scanners.scanner_dns import ScannerDns


class Command(BaseCommand):
    help = 'Try to find subdomains in various ways, some manually'

    def add_arguments(self, parser):
        parser.add_argument('url', nargs='+', type=str)

        parser.add_argument(
            '--manual',
            dest='manual',
            action='store_true',
            default=False,
            help='perform a manual dns scan',
        )

    def handle(self, *args, **options):
        if options['manual']:
            for url in options['url']:
                s = ScannerDns()
                s.manual_harvesting(url)
