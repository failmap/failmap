import logging

from django.core.management.base import BaseCommand

from failmap_admin.map.rating import add_organization_rating, rerate_urls
from failmap_admin.scanners.models import Url
from failmap_admin.scanners.scanner_tls_qualys import scan, scan_task

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

    def handle(self, *args, **options):
        if options['manual']:
            value = input("Type the url, without protocol:")
            url = Url.objects.all().filter(url=value).first()

            scan_task(url)

            rerate_urls([url])

            # url can be owned by many organizations:
            organizations = url.organization.all()
            for organization in organizations:
                add_organization_rating(organization=organization)
        else:
            while True:
                scan.apply()
