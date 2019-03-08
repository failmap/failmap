import logging
from argparse import ArgumentTypeError

from django.core.management.base import BaseCommand
from iso3166 import countries_by_alpha2

from websecmap.map.report import calculate_map_data

log = logging.getLogger(__package__)


class Command(BaseCommand):

    def add_arguments(self, parser):

        parser.add_argument("--days",
                            type=check_positive,
                            help="Number of days to go back in time.",
                            required=False)

        parser.add_argument("--country",
                            type=is_iso,
                            help="2 character iso code of country",
                            required=True)

    def handle(self, *args, **options):
        """ Short hand for the first time running this """

        if options['days']:
            days = options['days']
        else:
            days = 366

        calculate_map_data(days, country=[options['country']])


def check_positive(value):
    ivalue = int(value)
    if ivalue <= 0:
        raise ArgumentTypeError("%s is an invalid positive int value" % value)
    return ivalue


def is_iso(value):
    if value not in countries_by_alpha2:
        raise ArgumentTypeError("%s country should be a valid ISO code." % value)
    return value
