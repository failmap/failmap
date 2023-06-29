import logging
from datetime import datetime, timezone
from typing import Union, List

from django.core.management.base import BaseCommand

from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan
from websecmap.scanners.scanmetadata import get_backend_scanmetadata
from websecmap.scanners.scanner import chunks2

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Determines which scans are the latest and sets the latest scan flag. Normally this would happen automatically
    using the scan manager. But the flags are empty in older systems.

    The queries used allow sliding through time, for example setting the latest on a certain date. Which does not
    make sense at all, but works."""

    def handle(self, *args, **options):
        metadata = get_backend_scanmetadata()

        for scan_type in metadata["url_scan_types"]:
            reflag_urlgenericscan(scan_type=scan_type)

        for scan_type in metadata["endpoint_scan_types"]:
            reflag_endpointgenericscan(scan_type=scan_type)


def reflag_urlgenericscan(scan_type):
    log.debug("Setting flags on UrlGenericScan type: %s", scan_type)
    UrlGenericScan.objects.all().filter(type=scan_type).update(is_the_latest_scan=False)

    # get the latest scans
    sql = f"""
        SELECT
            id,
            last_scan_moment,
            is_the_latest_scan
        FROM scanners_urlgenericscan
        INNER JOIN
            (SELECT MAX(id) as id2 FROM scanners_urlgenericscan egs2
             WHERE last_scan_moment <= '{datetime.now(timezone.utc)}' and type = '{scan_type}' GROUP BY url_id
             ) as x
        ON x.id2 = scanners_urlgenericscan.id
    """

    updatescans(UrlGenericScan.objects.raw(sql))


def reflag_endpointgenericscan(scan_type):
    log.debug("Setting flags on EndpointGenericScan type: %s", scan_type)
    EndpointGenericScan.objects.all().filter(type=scan_type).update(is_the_latest_scan=False)

    # get the latest endpointgenericscans
    sql = f"""
        SELECT
            id,
            last_scan_moment,
            is_the_latest_scan
        FROM scanners_endpointgenericscan
        INNER JOIN
            (SELECT MAX(id) as id2 FROM scanners_endpointgenericscan egs2
             WHERE last_scan_moment <= '{datetime.now(timezone.utc)}' and type = '{scan_type}' GROUP BY endpoint_id
             ) as x
        ON x.id2 = scanners_endpointgenericscan.id
    """

    updatescans(EndpointGenericScan.objects.raw(sql))


def updatescans(scans: List[Union[UrlGenericScan, EndpointGenericScan]]) -> None:
    ids = [scan.id for scan in scans]
    log.debug("Updating %s scans", len(ids))

    # update per large batch of scans, so not to overload with an IN query with a million id's
    for chunk in chunks2(ids, 1000):
        EndpointGenericScan.objects.filter(id__in=chunk).update(is_the_latest_scan=True)

    # old and slower, but less error prone implementation:
    # for scan in scans:
    #     scan.is_the_latest_scan = True
    #     scan.save()
