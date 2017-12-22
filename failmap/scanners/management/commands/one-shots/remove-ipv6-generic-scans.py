import logging

from django.core.management.base import BaseCommand

from failmap.scanners.models import EndpointGenericScan

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'The dev machine can\'t perform ipv6 scans, but by accident we could have made some. ' \
           'This script removes all ipv6 generic scans from the database.'

    def handle(self, *args, **options):
        scans = EndpointGenericScan.objects.all()

        for scan in scans:
            if scan.endpoint.is_ipv6():
                print("Scan: %s Endpoint: %s IPv6: %s" %
                      (scan, scan.endpoint, scan.endpoint.is_ipv6()))
                # scan.delete()
