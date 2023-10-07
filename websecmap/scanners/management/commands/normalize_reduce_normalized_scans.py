import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.reduce_identical_scans import reduce_normalized_identical_scans

log = logging.getLogger(__package__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        # todo: add scan type parameter...
        reduce_normalized_identical_scans("dnssec")
