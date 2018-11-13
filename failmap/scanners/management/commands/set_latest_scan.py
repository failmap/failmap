import logging
from datetime import datetime

import pytz
from django.core.management.base import BaseCommand

from failmap.scanners.models import EndpointGenericScan, TlsQualysScan, TlsScan, UrlGenericScan

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Determines which scans are the latest and sets the latest scan flag. Normally this would happen automatically
    using the scan manager. But the flags are empty in older systems.

    The queries used allow sliding through time, for example setting the latest on a certain date. Which does not
    make sense at all, but works."""

    def handle(self, *args, **options):
        reflag_tlssscan()
        reflag_tls_qualysscan()
        reflag_urlgenericscan(type="DNSSEC")

        reflag_endpointgenericscan(type="X-XSS-Protection")
        reflag_endpointgenericscan(type="Strict-Transport-Security")
        reflag_endpointgenericscan(type="X-Frame-Options")
        reflag_endpointgenericscan(type="X-Content-Type-Options")
        reflag_endpointgenericscan(type="ftp")
        reflag_endpointgenericscan(type="plain_https")
        reflag_endpointgenericscan(type="tls_qualys_certificate_trusted")
        reflag_endpointgenericscan(type="tls_qualys_encryption_quality")


def reflag_tlssscan():
    log.debug("Setting flags on tlsscan type")

    TlsScan.objects.all().update(is_the_latest_scan=False)

    # get the latest scans
    sql = '''
        SELECT
            id,
            last_scan_moment,
            is_the_latest_scan
        FROM scanners_tlsscan
        INNER JOIN
            (SELECT MAX(id) as id2 FROM scanners_tlsscan egs2
             WHERE `last_scan_moment` <= '%(when)s' GROUP BY endpoint_id
             ) as x
        ON x.id2 = scanners_tlsscan.id
    ''' % {'when': datetime.now(pytz.utc)}

    updatescans(TlsScan.objects.raw(sql))


def reflag_tls_qualysscan():
    log.debug("Setting flags on tls_qualysscan type")
    TlsQualysScan.objects.all().update(is_the_latest_scan=False)

    # get the latest scans
    sql = '''
        SELECT
            id,
            last_scan_moment,
            is_the_latest_scan
        FROM scanner_tls_qualys
        INNER JOIN
            (SELECT MAX(id) as id2 FROM scanner_tls_qualys egs2
             WHERE `last_scan_moment` <= '%(when)s' GROUP BY endpoint_id
             ) as x
        ON x.id2 = scanner_tls_qualys.id
    ''' % {'when': datetime.now(pytz.utc)}

    updatescans(TlsQualysScan.objects.raw(sql))


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
