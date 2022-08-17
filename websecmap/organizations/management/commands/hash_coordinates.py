import logging

from django.core.management.base import BaseCommand

from websecmap.organizations.models import Coordinate

log = logging.getLogger(__package__)


class Command(BaseCommand):
    def handle(self, *args, **options):

        coordinates = Coordinate.objects.all()
        for coordinate in coordinates:
            coordinate.save()

        log.info("Done creating hashes for %s.", len(coordinates))
