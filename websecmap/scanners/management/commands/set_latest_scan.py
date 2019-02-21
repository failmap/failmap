import logging
from datetime import datetime

import pytz
from django.core.management.base import BaseCommand

from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan
from websecmap.scanners.types import ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Determines which scans are the latest and sets the latest scan flag. Normally this would happen automatically
    using the scan manager. But the flags are empty in older systems.

    The queries used allow sliding through time, for example setting the latest on a certain date. Which does not
    make sense at all, but works."""

    def handle(self, *args, **options):
        for scan_type in URL_SCAN_TYPES:
            reflag_urlgenericscan(type=scan_type)

        for scan_type in ENDPOINT_SCAN_TYPES:
            reflag_endpointgenericscan(type=scan_type)


def reflag_urlgenericscan(type):
    log.debug("Setting flags on UrlGenericScan type: %s" % type)
    UrlGenericScan.objects.all().filter(type=type).update(is_the_latest_scan=False)

    # get the latest scans
    sql = '''
        SELECT
            id,
            last_scan_moment,
            is_the_latest_scan
        FROM scanners_urlgenericscan
        INNER JOIN
            (SELECT MAX(id) as id2 FROM scanners_urlgenericscan egs2
             WHERE `last_scan_moment` <= '%(when)s' and type = '%(type)s' GROUP BY url_id
             ) as x
        ON x.id2 = scanners_urlgenericscan.id
    ''' % {'when': datetime.now(pytz.utc), 'type': type}

    updatescans(UrlGenericScan.objects.raw(sql))


def reflag_endpointgenericscan(type):
    log.debug("Setting flags on EndpointGenericScan type: %s" % type)
    EndpointGenericScan.objects.all().filter(type=type).update(is_the_latest_scan=False)

    # get the latest endpointgenericscans
    sql = '''
        SELECT
            id,
            last_scan_moment,
            is_the_latest_scan
        FROM scanners_endpointgenericscan
        INNER JOIN
            (SELECT MAX(id) as id2 FROM scanners_endpointgenericscan egs2
             WHERE `last_scan_moment` <= '%(when)s' and type = '%(type)s' GROUP BY endpoint_id
             ) as x
        ON x.id2 = scanners_endpointgenericscan.id
    ''' % {'when': datetime.now(pytz.utc), 'type': type}

    updatescans(EndpointGenericScan.objects.raw(sql))


def updatescans(scans):
    log.debug("Updating %s scans" % len(list(scans)))
    for scan in scans:
        scan.is_the_latest_scan = True
        scan.save()
