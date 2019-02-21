import logging

from django.core.management.base import BaseCommand

from websecmap.organizations.models import Coordinate

log = logging.getLogger(__package__)


class Command(BaseCommand):

    def handle(self, *args, **options):

        coordinates = Coordinate.objects.all().filter(geojsontype='Point')

        for coordinate in coordinates:
            a = coordinate.area
            coordinate.area = [a[1], a[0]]

            coordinate.edit_area = {
                "type": "Point",
                "coordinates": [a[1], a[0]]
            }

            log.debug("Switched %s" % coordinate.organization)
            coordinate.save()
