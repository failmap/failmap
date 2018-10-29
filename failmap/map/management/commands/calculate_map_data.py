import logging
from argparse import ArgumentTypeError

from django.core.management.base import BaseCommand

from failmap.map.rating import calculate_map_data

log = logging.getLogger(__package__)


class Command(BaseCommand):

    def add_arguments(self, parser):

        parser.add_argument("--days",
                            type=check_positive,
                            help="Number of days to go back in time.",
                            required=False)

    def handle(self, *args, **options):
        """ Short hand for the first time running this """

        if options['days']:
            days = options['days']
        else:
            days = 366

        calculate_map_data(days)


def check_positive(value):
    ivalue = int(value)
    if ivalue <= 0:
        raise ArgumentTypeError("%s is an invalid positive int value" % value)
    return ivalue
