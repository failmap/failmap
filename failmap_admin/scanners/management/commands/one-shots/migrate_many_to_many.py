from django.core.management.base import BaseCommand

from failmap_admin.map.determineratings import DetermineRatings
from failmap_admin.organizations.models import Organization
from failmap_admin.scanners.models import Url


# Only the latest ratings...
class Command(BaseCommand):
    help = 'Fill empty many to many relationship with the current values.'

    def handle(self, *args, **options):
        # urls = Url.objects.all()
        # for url in urls:
        #     url.organizations.add(url.organization)
        return