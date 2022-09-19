import logging
from datetime import datetime

import pytz
from django.core.management.base import BaseCommand

from websecmap.scanners.scanmetadata import ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Determines which scans are the latest and sets the latest scan flag. Normally this would happen automatically
    using the scan manager. But the flags are empty in older systems.

    The queries used allow sliding through time, for example setting the latest on a certain date. Which does not
    make sense at all, but works."""

    def handle(self, *args, **options):
        for scan_type in URL_SCAN_TYPES:
            reflag_urlgenericscan(scan_type=scan_type)

        for scan_type in ENDPOINT_SCAN_TYPES:
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
             WHERE last_scan_moment <= '{datetime.now(pytz.utc)}' and type = '{scan_type}' GROUP BY url_id
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
             WHERE last_scan_moment <= '{datetime.now(pytz.utc)}' and type = '{scan_type}' GROUP BY endpoint_id
             ) as x
        ON x.id2 = scanners_endpointgenericscan.id
    """

    updatescans(EndpointGenericScan.objects.raw(sql))


def updatescans(scans):
    log.debug("Updating %s scans", len(list(scans)))
    for scan in scans:
        scan.is_the_latest_scan = True
        scan.save()
