import json
import logging

from django.core.management.base import BaseCommand

from websecmap.organizations.datasources.dutch_government import parse_data

log = logging.getLogger(__package__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        ministries = {
            "description": "Dutch ministries",
            "layer": "government",
            "country": "NL",
            "xml_plural": "organisaties",
            "xml_single": "organisatie",
        }

        data = parse_data(ministries, "exportOO.xml")
        print(json.dumps(data, indent=2))
