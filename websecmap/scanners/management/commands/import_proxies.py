import logging

import iso3166
from django.core.management.base import BaseCommand

from websecmap.scanners.find_scanproxies import find

log = logging.getLogger(__name__)


def valid_country_code(code):

    # let's hope openproxy.space does use iso3166 :)
    if code not in iso3166.countries_by_alpha2:
        raise ValueError("Countrycode not present in iso3166: %s" % code)

    return code


class Command(BaseCommand):
    """Imports proxies from openproxy.space"""

    def add_arguments(self, parser):
        parser.add_argument('countries', nargs='*', help='From what countries? Country code: NL, BE, ...',
                            type=valid_country_code)
        super().add_arguments(parser)

    def handle(self, *args, **options):
        find(options['countries'], amount=50)
