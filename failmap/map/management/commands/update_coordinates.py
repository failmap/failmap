import logging
from argparse import ArgumentTypeError
from datetime import datetime

from django.core.management.base import BaseCommand

from failmap.map.geojson import update_coordinates

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = "Connects to OSM and gets a set of coordinates."

    def add_arguments(self, parser):
        parser.add_argument("--date",
                            help="Date since when the import should be effective. - format YYYY-MM-DD",
                            required=False,
                            type=valid_date)

        parser.add_argument("--country",
                            help="Country code. Eg: NL, DE, EN",
                            required=False)

        parser.add_argument("--region",
                            help="Region: municipality, province, water\ board ...",
                            required=False)

    # https://nl.wikipedia.org/wiki/Gemeentelijke_herindelingen_in_Nederland#Komende_herindelingen
    def handle(self, *app_labels, **options):

        update_coordinates(when=options["date"], country=options["country"], organization_type=options["region"])


def valid_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise ArgumentTypeError(msg)
