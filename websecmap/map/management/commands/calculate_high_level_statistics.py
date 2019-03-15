import logging
from argparse import ArgumentTypeError

from django.core.management.base import BaseCommand
from iso3166 import countries_by_alpha2

from websecmap.map.report import calculate_high_level_stats

log = logging.getLogger(__package__)


class CalculateCommand(BaseCommand):
    command = None

    def add_arguments(self, parser):

        parser.add_argument("--days",
                            type=check_positive,
                            help="Number of days to go back in time.",
                            required=False)

        parser.add_argument("--country",
                            type=is_iso,
                            help="2 character iso code of country",
                            required=False)

        parser.add_argument("--organization_type",
                            type=str,
                            help="name of the organization type",
                            required=False)

    def handle(self, *args, **options):
        """ Short hand for the first time running this """

        if options['days']:
            days = options['days']
        else:
            days = 366

        if options['country']:
            countries = [options['country']]
        else:
            countries = []

        if options['organization_type']:
            organization_type = [options['organization_type']]
        else:
            organization_type = []

        if not CalculateCommand.command:
            log.debug("No command given for calculations")

        CalculateCommand.command(days=days, countries=countries, organization_types=organization_type)


class Command(CalculateCommand):
    CalculateCommand.command = calculate_high_level_stats


def check_positive(value):
    ivalue = int(value)
    if ivalue <= 0:
        raise ArgumentTypeError("%s is an invalid positive int value" % value)
    return ivalue


def is_iso(value):
    if value not in countries_by_alpha2:
        raise ArgumentTypeError("%s country should be a valid ISO code." % value)
    return value
