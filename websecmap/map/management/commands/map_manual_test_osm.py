import logging

import requests
from django.core.management.base import BaseCommand

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = "Connects to OSM and gets a set of coordinates."

    # https://nl.wikipedia.org/wiki/Gemeentelijke_herindelingen_in_Nederland#Komende_herindelingen
    def handle(self, *app_labels, **options):

        country = "NL"
        admin_level = 8

        query = f"""area["ISO3166-2"~"^{country}"]->.gem; relation(area.gem)[type=boundary]
        [boundary=administrative][admin_level={admin_level}]; out geom;"""

        log.debug(f"Performing overpass query {query}.")
        response = requests.post(
            "http://www.overpass-api.de/api/interpreter",
            data={"data": query, "submit": "Query"},
            stream=True,
            timeout=(1200, 1200),
        )

        log.debug("Response from server:")
        log.info(f"{response.content[0:250]}")
        response.raise_for_status()

        log.info("Test completed successfully.")
