from django.core.management.base import BaseCommand

from failmap_admin.map.determineratings import DetermineRatings
from failmap_admin.organizations.models import Organization
from failmap_admin.scanners.models import Url


# Only the latest ratings...
class Command(BaseCommand):
    help = 'Rate all urls and organizations.'

    def handle(self, *args, **options):
        dr = DetermineRatings()
        dr.rate_urls()
        dr.rate_organizations()

        # o = Organization.objects.all()
        # for organization in o:
        #    urls = Url.objects.filter(organization=organization)
        #    dr = DetermineRatings()
        #    for url in urls:
        #        dr.rate_url(url=url)
        #
        #    dr.rate_organization(organization=organization)
