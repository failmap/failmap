from django.core.management.base import BaseCommand

from failmap_admin.map.determineratings import (default_ratings, rate_organizations_efficient,
                                                rerate_existing_urls)
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
        rerate_existing_urls()

        OrganizationRating.objects.all().delete()
        default_ratings()
        rate_organizations_efficient(create_history=True)
