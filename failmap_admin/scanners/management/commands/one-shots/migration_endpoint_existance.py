import datetime

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.scanners.models import TlsQualysScan

# This script estimates when an URL started to exist, and when endpoints started to exist.
# This is created when discovered the Endpoint data was not complete enough: missing "when"
# the endpoint was created. Without it, it could not be easily determined what endpoints where
# alive at what moment to give accurate history.


class Command(BaseCommand):
    help = 'Create some discovery dates for endpoints. Only run this once after migration.'

    def handle(self, *args, **options):
        # We will find out what the first scan date was
        # for the endpoint, and take that as the discovery date of the endpoint.
        # probably all endpoints will then have a "discovery" date.
        # with that date we can figure out what time an endpoint existed.

        # During development found something strange:
        # Create date column, with null and empty. The date of for the column will then be today.
        # BUT if you then migrate that empty column from date to datetime, it's empty as it's
        # supposed to. Oh well...

        scans = TlsQualysScan.objects.all().order_by("rating_determined_on")
        for scan in scans:
            try:
                print(scan.endpoint.discovered_on)
                if not scan.endpoint.discovered_on:
                    print("Updating %s" % scan.endpoint)
                    scan.endpoint.discovered_on = scan.rating_determined_on
                    scan.endpoint.save()
            except ObjectDoesNotExist:
                print("Scan does not have an endpoint! %s " % scan)
