import logging

from django.core.management.base import BaseCommand

from websecmap.map.logic.coordinates import repair_corrupted_coordinate
from websecmap.organizations.models import Coordinate

log = logging.getLogger(__package__)


class Command(BaseCommand):

    def handle(self, *args, **options):

        coordinates = Coordinate.objects.all().filter(geojsontype='Point')

        for coordinate in coordinates:
            repair_corrupted_coordinate(coordinate)
