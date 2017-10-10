from django.core.management.base import BaseCommand

from failmap_admin.map.determineratings import DetermineRatings


class Command(BaseCommand):
    help = 'Rate all urls and organizations. Latest rating only.'

    def handle(self, *args, **options):
        dr = DetermineRatings()
        dr.rate_urls()
        dr.rate_organizations()
