import logging

from django.core.management.base import BaseCommand

from failmap.map.rating import calculate_map_data

log = logging.getLogger(__package__)


class Command(BaseCommand):

    def handle(self, *args, **options):
        """ Short hand for the first time running this """

        calculate_map_data()
