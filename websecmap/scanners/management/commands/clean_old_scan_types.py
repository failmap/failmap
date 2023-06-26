import logging

from websecmap.app.management.commands._private import VerifyTaskCommand
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan
from websecmap.scanners.scanmetadata import get_backend_scanmetadata

log = logging.getLogger(__name__)


class Command(VerifyTaskCommand):
    """Removes scan types not in the scanners."""

    help = __doc__

    def handle(self, *args, **options):
        metadata = get_backend_scanmetadata()

        log.info("Deleting not used scan types.")

        deleted = EndpointGenericScan.objects.all().filter().exclude(type__in=metadata["endpoint_scan_types"]).delete()
        log.info(deleted)

        deleted = UrlGenericScan.objects.all().filter().exclude(type__in=metadata["url_scan_types"]).delete()
        log.info(deleted)

        log.info("Done")
