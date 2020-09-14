import logging

from websecmap.app.management.commands._private import VerifyTaskCommand
from websecmap.scanners import ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan

log = logging.getLogger(__name__)


class Command(VerifyTaskCommand):
    """Removes scan types not in the scanners."""

    help = __doc__

    def handle(self, *args, **options):
        log.info("Deleting not used scan types.")

        deleted = EndpointGenericScan.objects.all().filter().exclude(type__in=ENDPOINT_SCAN_TYPES).delete()
        log.info(deleted)

        deleted = UrlGenericScan.objects.all().filter().exclude(type__in=URL_SCAN_TYPES).delete()
        log.info(deleted)

        log.info("Done")
