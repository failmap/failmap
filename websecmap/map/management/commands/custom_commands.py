import logging
from argparse import ArgumentTypeError
from typing import Callable

from django.core.management.base import BaseCommand
from iso3166 import countries_by_alpha2

log = logging.getLogger(__package__)


class CalculateCommand(BaseCommand):
    # Set a sample callable for the command, this will be overridden by implementations
    command: Callable = lambda days, countries, organization_types: f"{days}{countries}{organization_types}"

    def add_arguments(self, parser):

        parser.add_argument("--days", type=check_positive, help="Number of days to go back in time.", required=False)

        parser.add_argument("--country", type=is_iso, help="2 character iso code of country", required=False)

        parser.add_argument("--organization_type", type=str, help="name of the organization type", required=False)

    def handle(self, *args, **options):
        """Short hand for the first time running this"""

        if options["days"]:
            days = options["days"]
        else:
            days = 366

        if options["country"]:
            countries = [options["country"]]
        else:
            countries = []

        if options["organization_type"]:
            organization_type = [options["organization_type"]]
        else:
            organization_type = []

        if not CalculateCommand.command:
            log.debug("No command given for calculations")

        CalculateCommand.command(days=days, countries=countries, organization_types=organization_type)


def check_positive(value):
    ivalue = int(value)
    if ivalue <= 0:
        raise ArgumentTypeError(f"{value} is an invalid positive int value")
    return ivalue


def is_iso(value):
    if value not in countries_by_alpha2:
        raise ArgumentTypeError(f"{value} country should be a valid ISO code.")
    return value
