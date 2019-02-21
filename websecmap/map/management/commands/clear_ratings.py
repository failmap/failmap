import logging

from django.core.management.base import BaseCommand

from websecmap.map.models import OrganizationRating, UrlRating

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Deletes ratings from the database. They can be rebuild based on available scanner data.'

    def handle(self, *args, **options):
        log.info("Ratings can be rebuilt from the available scans in the database.")
        OrganizationRating.objects.all().delete()
        UrlRating.objects.all().delete()
