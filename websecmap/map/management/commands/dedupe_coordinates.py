import logging

from django.core.management.base import BaseCommand

from websecmap.map.logic.coordinates import dedupe_coordinates

log = logging.getLogger(__package__)


class Command(BaseCommand):

    def handle(self, *args, **options):

        dedupe_coordinates()
