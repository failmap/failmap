from django.core.management.base import BaseCommand, CommandError

from failmap_admin.map.determineratings import DetermineRatings
from failmap_admin.organizations.models import Organization
from failmap_admin.scanners.models import Url
from failmap_admin.scanners.scanner_tls_qualys import ScannerTlsQualys


class Command(BaseCommand):
    help = 'Perform scans, start somewhere and just go!'

    # https://docs.djangoproject.com/en/1.11/howto/custom-management-commands/
    # def add_arguments(self, parser):
    #    parser.add_argument('poll_id', nargs='+', type=int)

    def handle(self, *args, **options):
        # todo: figure out a way to "resume" from the last scanned organization,
        # since it can take a while to do the whole circle of organizations...
        # if we take the last scanned url to resume... could have consequences form
        # the admin interface, that's not good.
        o = Organization.objects.all()
        for organization in o:
            urls_to_scan = []
            urls = Url.objects.filter(organization=organization)
            for url in urls:
                urls_to_scan.append(url.url)

            # scan per organization, to lower the amount of time for updates
            s = ScannerTlsQualys()
            s.scan(urls_to_scan)

            # the scanner still ends sequentially, so... we can now update the ratings
            # for some reason (probably caching?) urls are rated separately from organization
            dr = DetermineRatings()
            for url in urls:
                dr.rate_url(url=url)

            dr.rate_organization(organization=organization)
