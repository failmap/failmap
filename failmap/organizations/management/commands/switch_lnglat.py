import logging
from datetime import datetime
from typing import List

import pytz
from django.core.management.base import BaseCommand

from failmap.organizations.models import Organization, Url, Coordinate
from failmap.scanners.scanner.dns import discover_wildcard
from failmap.scanners.scanner.http import resolves
import json

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

            coordinate.save()
