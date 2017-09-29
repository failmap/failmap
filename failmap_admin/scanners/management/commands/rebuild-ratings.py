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
        UrlRating.objects.all().delete()
        DetermineRatings.rate_urls_efficient(create_history=True)
        DetermineRatings.rate_urls_efficient()  # this should not do anything anymore...

        OrganizationRating.objects.all().delete()
        DetermineRatings.rate_organizations_efficient(create_history=True)
        print("Making the most recent organization rating, should not have any effect.")
        DetermineRatings.rate_organizations_efficient()  # this should not do anything anymore...
