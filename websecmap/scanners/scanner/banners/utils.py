from datetime import datetime, timedelta, timezone
from typing import List

from websecmap.app.constance import constance_cached_value
from websecmap.scanners.models import EndpointGenericScan, UrlIp
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.banners.detect_version import SERVICE_IDENTITY_NOT_SEEN_IN_A_WHILE


def clean_old_bannergrab_results():
    #  connect the finding to the urls that have this IP, this can be a lot of urls
    #  Things that have not seen for a while will be deleted. EndpointGenericScan of this type older than 7 days
    # means that it has not been seen. All the other values are auto-update etc. The amount of days depends on how
    # many times this scan is run. The data is not really stable. Probably is a lot blocks ands such. If it's blocked
    # then so be it. Might not be blocked after a day or two...

    clean_old_results(scan_types=["bannergrab", "bannergrab_masscan"])
    # How do you know if the endpoint still exists? It will have no data attached to it when there is no
    # issue, so that will not be shown. Not an issue.


def clean_old_results(scan_types: List[str]):
    #  connect the finding to the urls that have this IP, this can be a lot of urls
    #  Things that have not seen for a while will be deleted. EndpointGenericScan of this type older than 7 days
    # means that it has not been seen. All the other values are auto-update etc. The amount of days depends on how
    # many times this scan is run. The data is not really stable. Probably is a lot blocks ands such. If it's blocked
    # then so be it. Might not be blocked after a day or two...
    old_scans = datetime.now(timezone.utc) - timedelta(
        days=constance_cached_value("BANNERGRAB_DAYS_TO_OUTDATED_METRIC")
    )
    old_epgs = EndpointGenericScan.objects.all().filter(type__in=scan_types, last_scan_moment__lte=old_scans)

    # When there's new stuff it will show up automatically
    for old_epg in old_epgs:
        store_endpoint_scan_result(
            scan_type=old_epg.type,
            endpoint_id=old_epg.endpoint.id,
            rating=SERVICE_IDENTITY_NOT_SEEN_IN_A_WHILE,
            evidence="",
            message="",
        )


def get_urls_by_ip(ip):
    # only get current ip's otherwise there will be conclusions tied to stuff that only resolved to a certain
    # ip in the past. We've seen happening that a certain ip was resolved, and which was used in the past
    # on a series of other hosts. This happens when a server gets migrated to another ip for example.
    # - in this specific case we saw one new metric from the new ip and one from the old ip right after each other.
    # todo: a host can have multiple ip's, so when scraping ip's just see if one of the A records is one that is
    # in the database.
    return UrlIp.objects.all().filter(ip=ip, is_unused=False).only("id", "url", "url__id")
