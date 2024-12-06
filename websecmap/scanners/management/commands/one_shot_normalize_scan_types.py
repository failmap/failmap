import logging

from websecmap.app.management.commands._private import VerifyTaskCommand
from websecmap.scanners.models import EndpointGenericScan

log = logging.getLogger(__name__)


class Command(VerifyTaskCommand):
    """
    Changes scan types with weird characters into a slug that can also be used in javascript.

    This fixes a mismatch between these two worlds: and stops you thinking what scan is what.
    """

    help = __doc__

    def handle(self, *args, **options):
        scans = EndpointGenericScan.objects.all().filter(
            type__in=["Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options", "X-XSS-Protection"]
        )

        for scan in scans:
            old_type = scan.type
            new_type = f"http_security_header_{str(old_type).lower().replace('-', '_')}"
            log.debug("Old: %s, New: %s", old_type, new_type)
            scan.type = new_type
            scan.save(update_fields=["type"])
