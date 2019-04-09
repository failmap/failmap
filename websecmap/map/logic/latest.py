from django.contrib.humanize.templatetags.humanize import naturaltime
from django.utils import timezone

from websecmap.map.logic.map_defaults import get_country, get_organization_type, remark
from websecmap.reporting.severity import get_severity
from websecmap.scanners import ALL_SCAN_TYPES, ENDPOINT_SCAN_TYPES, URL_SCAN_TYPES
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan


def get_all_latest_scans(country, organization_type):
    scans = {}

    dataset = {
        "scans": {},
        "render_date": timezone.now().isoformat(),
        "remark": remark,
    }

    for scan_type in ENDPOINT_SCAN_TYPES:
        scans[scan_type] = list(EndpointGenericScan.objects.filter(
            type=scan_type,
            endpoint__url__organization__type=get_organization_type(organization_type),
            endpoint__url__organization__country=get_country(country)
        ).order_by('-rating_determined_on')[0:6])

    for scan_type in URL_SCAN_TYPES:
        scans[scan_type] = list(UrlGenericScan.objects.filter(
            type=scan_type,
            url__organization__type=get_organization_type(organization_type),
            url__organization__country=get_country(country)
        ).order_by('-rating_determined_on')[0:6])

    for scan_type in ALL_SCAN_TYPES:

        dataset["scans"][scan_type] = []

        for scan in scans[scan_type]:
            calculation = get_severity(scan)

            if scan_type in URL_SCAN_TYPES:
                # url scans
                dataset["scans"][scan_type].append({
                    "url": scan.url.url,
                    "service": "%s" % scan.url.url,
                    "protocol": scan_type,
                    "port": "-",
                    "ip_version": "-",
                    "explanation": calculation.get("explanation", ""),
                    "high": calculation.get("high", 0),
                    "medium": calculation.get("medium", 0),
                    "low": calculation.get("low", 0),
                    "last_scan_humanized": naturaltime(scan.last_scan_moment),
                    "last_scan_moment": scan.last_scan_moment.isoformat()
                })
            else:
                # endpoint scans
                dataset["scans"][scan_type].append({
                    "url": scan.endpoint.url.url,
                    "service": "%s/%s (IPv%s)" % (scan.endpoint.protocol, scan.endpoint.port, scan.endpoint.ip_version),
                    "protocol": scan.endpoint.protocol,
                    "port": scan.endpoint.port,
                    "ip_version": scan.endpoint.ip_version,
                    "explanation": calculation.get("explanation", ""),
                    "high": calculation.get("high", 0),
                    "medium": calculation.get("medium", 0),
                    "low": calculation.get("low", 0),
                    "last_scan_humanized": naturaltime(scan.last_scan_moment),
                    "last_scan_moment": scan.last_scan_moment.isoformat()
                })

    return dataset
