import logging

from django.core.management.base import BaseCommand

from failmap_admin.celery import PRIO_HIGH
from failmap_admin.scanners.models import Url
from failmap_admin.scanners.scanner_tls_qualys import scan, scan_new_urls, scan_urls

logger = logging.getLogger(__package__)


# https://docs.djangoproject.com/en/1.11/howto/custom-management-commands/
class Command(BaseCommand):
    help = 'Perform scans, start somewhere and just go!'

    def add_arguments(self, parser):
        parser.add_argument(
            '--manual', '-m',
            help="Give an url to scan via command line.",
            nargs=1,
            required=False,
            default=False,
            type=bool
        )

        parser.add_argument(
            '--new',
            help="Only scan new urls.",
            type=bool
        )

    def handle(self, *args, **options):
        if options['manual']:
            value = input("Type the url, without protocol:")
            url = Url.objects.all().filter(url=value).first()
            scan_urls(urls=[url], priority=PRIO_HIGH)
        else:

            if options['new']:
                scan_new_urls.apply()
            else:
                # removed the infinite loop, so to allow scheduling.
                scan.apply()
