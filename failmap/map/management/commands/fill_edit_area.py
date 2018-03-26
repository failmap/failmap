import logging

from django.core.management.base import BaseCommand

from failmap.organizations.models import Coordinate

logger = logging.getLogger(__package__)


class Command(BaseCommand):

    def handle(self, *args, **options):

        coords = Coordinate.objects.all()
        for coord in coords:

            if not coord.edit_area:

                if coord.geojsontype and coord.area:
                    coord.edit_area = {"type": coord.geojsontype, "coordinates": coord.area}
                    coord.save()