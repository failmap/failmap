import logging
from datetime import datetime, timezone
from typing import List, Union

from django.core.management.base import BaseCommand

from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan
from websecmap.scanners.scanmetadata import get_backend_scanmetadata
from websecmap.scanners.scanner import chunks2

log = logging.getLogger(__name__)

"""
    The following approach is not possible, as MySQL does not allow you to specify the target table if you also
    use that same table in a select. understabdable somewhere. But then we need a temporary table and still
    do the same stuff we're already doing with joining stuff on id's which is slow. So there is little profit
    going down that road.

    See:
    ERROR 1093 (HY000): You can't specify target table 'scanners_endpointgenericscan' for update in FROM clause

    UPDATE
        scanners_endpointgenericscan
    SET
        is_the_latest_scan = 1
    WHERE id IN (
        SELECT
            id
        FROM scanners_endpointgenericscan
        INNER JOIN
            (SELECT MAX(id) as id2 FROM scanners_endpointgenericscan egs2
             WHERE last_scan_moment <= '{datetime.now(timezone.utc)}' and type = '{scan_type}' GROUP BY endpoint_id
             ) as x
        ON x.id2 = scanners_endpointgenericscan.id
    )
"""


class Command(BaseCommand):
    """Determines which scans are the latest and sets the latest scan flag. Normally this would happen automatically
    using the scan manager. But the flags are empty in older systems.

    The queries used allow sliding through time, for example setting the latest on a certain date. Which does not
    make sense at all, but works."""

    def add_arguments(self, parser):
        parser.add_argument(
            "scan_type", nargs="*", help="The scan type to reflag, use 'all' to reflag all.", choices=valid_scan_types()
        )
        super().add_arguments(parser)

    def handle(self, *args, **options):
        metadata = get_backend_scanmetadata()

        if "scan_type" not in options or "all" in options["scan_type"]:
            selected_scan_types = metadata["url_scan_types"] + metadata["endpoint_scan_types"]
        else:
            selected_scan_types = options["scan_type"]

        for scan_type in metadata["url_scan_types"]:
            if scan_type not in selected_scan_types:
                continue
            reflag_urlgenericscan(scan_type=scan_type)

        for scan_type in metadata["endpoint_scan_types"]:
            if scan_type not in selected_scan_types:
                continue
            reflag_endpointgenericscan(scan_type=scan_type)


def valid_scan_types():
    metadata = get_backend_scanmetadata()
    return list(sorted(metadata["url_scan_types"] + metadata["endpoint_scan_types"] + ["all"]))


def reflag_urlgenericscan(scan_type):
    log.info("Setting flags on UrlGenericScan type: %s", scan_type)
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

    updatescans(UrlGenericScan.objects.raw(sql), "url")


def reflag_endpointgenericscan(scan_type):
    log.info("Setting flags on EndpointGenericScan type: %s", scan_type)
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

    updatescans(EndpointGenericScan.objects.raw(sql), "endpoint")


def updatescans(scans: List[Union[UrlGenericScan, EndpointGenericScan]], generictype: str = "endpoint") -> None:
    ids = [scan.id for scan in scans]
    log.debug("Updating %s scans", len(ids))

    # update per large batch of scans, so not to overload with an IN query with a million id's
    for chunk in chunks2(ids, 1000):
        if generictype == "endpoint":
            EndpointGenericScan.objects.filter(id__in=chunk).update(is_the_latest_scan=True)
        elif generictype == "url":
            UrlGenericScan.objects.filter(id__in=chunk).update(is_the_latest_scan=True)

    # old and slower, but less error prone implementation:
    # for scan in scans:
    #     scan.is_the_latest_scan = True
    #     scan.save()
