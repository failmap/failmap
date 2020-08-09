import logging

from django.core.management.base import BaseCommand

from websecmap.map.logic.coordinates import move_coordinates_to_country
from websecmap.map.models import Configuration
from websecmap.organizations.models import Coordinate

log = logging.getLogger(__package__)


class Command(BaseCommand):

    def handle(self, *args, **options):

        # list(set( fixes distinct: django.db.utils.NotSupportedError:
        #   DISTINCT ON fields is not supported by this database backend
        countries = list(set(Configuration.objects.all().values_list('country', flat=True)))
        log.debug(countries)

        for country in countries:
            coordinates = Coordinate.objects.all().filter(geojsontype='Point', organization__country=country)
            move_coordinates_to_country(coordinates, country)
