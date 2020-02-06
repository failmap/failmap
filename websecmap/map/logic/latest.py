from collections import defaultdict

from django.contrib.humanize.templatetags.humanize import naturaltime
from django.db.models import Count, Q
from django.utils import timezone

from websecmap.map.logic.map_defaults import get_country, get_organization_type, remark
from websecmap.map.report import PUBLISHED_ENDPOINT_SCAN_TYPES, PUBLISHED_URL_SCAN_TYPES
from websecmap.reporting.severity import get_severity
from websecmap.scanners.models import EndpointGenericScan, UrlGenericScan


def get_all_latest_scans(country, organization_type):

    dataset = {
        "scans": defaultdict(list),
        "render_date": timezone.now().isoformat(),
        "remark": remark,
    }

    filtered_organization_type = get_organization_type(organization_type)
    filtered_country = get_country(country)

    # Really get the latest, without double results that apply for multiple organizations.
    # Do not show anything that is dead, on any level.
    for scan_type in PUBLISHED_ENDPOINT_SCAN_TYPES:
        scans = EndpointGenericScan.objects.filter(
            type=scan_type,
            is_the_latest_scan=True,
        ).annotate(
            n_urls=Count(
                'endpoint',
                filter=Q(
                    endpoint__is_dead=False,
                    endpoint__url__not_resolvable=False,
                    endpoint__url__is_dead=False,
                    endpoint__url__organization__is_dead=False,
                    endpoint__url__organization__country=filtered_country,
                    endpoint__url__organization__type_id=filtered_organization_type
                )
            )
        ).filter(
            n_urls__gte=1
        ).order_by(
            '-rating_determined_on'
        ).only('endpoint__url__url', 'endpoint__protocol', 'endpoint__port', 'endpoint__ip_version',
               'rating', 'type', 'explanation')[0:20]

        for scan in scans:
            calculation = get_severity(scan)

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

    for scan_type in PUBLISHED_URL_SCAN_TYPES:

        scans = UrlGenericScan.objects.filter(
            type=scan_type,
            is_the_latest_scan=True,
        ).annotate(
            n_urls=Count(
                'url',
                filter=Q(
                    url__organization__is_dead=False,
                    url__organization__country=filtered_country,
                    url__organization__type_id=filtered_organization_type,
                    url__is_dead=False,
                    url__not_resolvable=False,
                )
            )
        ).filter(n_urls=1).order_by('-rating_determined_on')[0:6]

        for scan in scans:
            calculation = get_severity(scan)

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

    return dataset
