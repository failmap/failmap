import logging
from argparse import ArgumentTypeError
from datetime import datetime

from django.core.management.base import BaseCommand

from websecmap.map.logic.openstreetmap import import_from_scratch
from websecmap.map.models import AdministrativeRegion

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = (
        "Connects to OSM and gets a set of coordinates. Example:"
        "failmap import_coordinates --country=SE --region=municipality --date=2018-01-01"
    )

    # NL, province: failmap import_coordinates --country=NL --region=province --date=2018-01-01
    # LU, all: failmap import_coordinates --country=LU --date=2018-01-01
    # all, all... which you don't want(!) :) : failmap import_coordinates --date=2018-01-01

    def add_arguments(self, parser):
        parser.add_argument("--country", help="Country code. Eg: NL, DE, EN", required=False)

        parser.add_argument("--region", help="Region: municipality, province, water board ...", required=False)

        parser.add_argument(
            "--date",
            help="Date since when the import should be effective. - format YYYY-MM-DD",
            required=False,
            type=valid_date,
        )

        parser.add_argument(
            "--list", help="Lists the currently available regions and countries.", required=False, action="store_true"
        )

    # https://nl.wikipedia.org/wiki/Gemeentelijke_herindelingen_in_Nederland#Komende_herindelingen
    def handle(self, *app_labels, **options):
        if options["list"]:
            log.info("Currently available administrative regions:")
            log.info("Hint: add the via the admin interface.")
            adminregions = AdministrativeRegion.objects.all()
            if not adminregions:
                log.info("-- None found. Add them via the admin interface.")

            for region in adminregions:
                log.info("%-3s %-72s, %-5s", region.country, region.organization_type, region.admin_level)

        else:
            import_from_scratch(
                countries=[options["country"]], organization_types=[options["region"]], when=options["date"]
            )


def valid_date(string):
    try:
        return datetime.strptime(string, "%Y-%m-%d")
    except ValueError as exc:
        msg = f"Not a valid date: '{string}'."
        raise ArgumentTypeError(msg) from exc
