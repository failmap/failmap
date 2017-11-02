import logging

from django.core.management.base import BaseCommand

from failmap_admin.map.determineratings import rate_organization_efficient, rerate_url_with_timeline
from failmap_admin.scanners import scanner_tls_qualys
from failmap_admin.scanners.models import Url

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Perform scans, start somewhere and just go!'

    # https://docs.djangoproject.com/en/1.11/howto/custom-management-commands/
    # def add_arguments(self, parser):
    #    parser.add_argument('poll_id', nargs='+', type=int)

    def add_arguments(self, parser):
        parser.add_argument(
            '--manual', '-o',
            help="Give an url to scan via command line.",
            nargs=1,
            required=False,
            default=False,
            type=bool
        )

    do_scan = True
    do_rate = True

    def handle(self, *args, **options):
        if options['manual']:
            url = input("Type the url, without protocol:")
            url = Url.objects.all().filter(url=url).first()

            s = scanner_tls_qualys.ScannerTlsQualys()
            s.scan([url.url])

            rerate_url_with_timeline(url=url)
            rate_organization_efficient(organization=url.organization)
        else:
            while True:
                scanner_tls_qualys.scan.apply()
