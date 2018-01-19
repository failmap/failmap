import logging

from django.core.management.base import BaseCommand

from ...geojson import update_coordinates

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = "Connects to OSM and gets a set of coordinates."

    # https://nl.wikipedia.org/wiki/Gemeentelijke_herindelingen_in_Nederland#Komende_herindelingen
    # Running this every month is fine too :)
    def handle(self, *app_labels, **options):
        # trace = input()
        update_coordinates()
