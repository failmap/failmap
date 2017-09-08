from django.core.management.base import BaseCommand

from failmap_admin.map.determineratings import DetermineRatings
from failmap_admin.map.models import OrganizationRating, UrlRating


# Remove ALL organization and URL ratings and rebuild them
class Command(BaseCommand):
    help = "Remove all organization and url ratings, then rebuild them from scratch. " \
           "This can take a while."

    # history
    # this has been made when a bug caused hunderds of thousands of ratings, slowing the top fail
    # The history code was present already to make the history for the map.
    # It has now been refactored into a command, so it's easier to work with.

    def handle(self, *args, **options):
        print("Deleting ALL url ratings")
        UrlRating.objects.all().delete()
        print("Deleting ALL organization ratings")
        OrganizationRating.objects.all().delete()

        # This will create 52 weeks of N urls ratings. (2000 urls = 100.000 ratings)
        # similar to organizations: 52 weeks of N organization (389 * 52 = 20.000 ratings)
        # When the previous rating is the same as the current one, the rating will not be saved.
        # So this is the real amount of data:
        # urls: 11946 (saving 85% by deduplication)
        # organizations: 20564 (saving NOTHING by deduplication)
        dr = DetermineRatings()

        # this makes a rating every 7 days, if there are new things to record.
        dr.rate_urls(create_history=True)
        dr.rate_organizations(create_history=True)

        # add a rating for today
        dr.rate_urls()
        dr.rate_organizations()
