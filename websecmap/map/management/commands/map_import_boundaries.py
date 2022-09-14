import logging

from django.core.management.base import BaseCommand

from websecmap.map.logic.openstreetmap import download_geojson_data, store_new

log = logging.getLogger(__package__)


class Command(BaseCommand):
    # Example usage: To update all coordinates on the 1st day of the year:
    # map_update_coordinates --url=https://osm-boundaries.com/Download/Submit?apiKey=... --country=NL --layer=government
    help = "map_import_boundaries ."

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            help="osm-boundaries to get data from, has to include the api key and has to be ready to use",
            required=False,
            type=str,
        )

        parser.add_argument("--country", help="The country to add the new shapes to", type=str, required=True)

        parser.add_argument("--layer", help="The layer to add the new shapes into", type=str, required=True)

    def handle(self, *app_labels, **options):
        data = download_geojson_data(options["url"])
        for feature in data["features"]:
            store_new(feature, country=options["country"], organization_type=options["layer"])
