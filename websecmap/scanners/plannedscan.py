import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytz
from django.db import connection

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, PlannedScan

log = logging.getLogger(__name__)


def progress(days=7) -> List[Dict[str, Any]]:
    """
    Retrieves the progress of all scans in the past 7 days. Will show how many are requested and how many
    are at what state.

    This routine is as simple and fast as it gets. The consumer will have to iterated and aggregate where needed.
    """

    when = datetime.utcnow() - timedelta(days=days)

    # i'm _DONE_ with the obscuring of group_by and counts using terrible abstractions.
    # so here is a raw query that just works on all databases and is trivially simple to understand.
    sql = """SELECT
                scanner, activity, state, count(*) as amount
            FROM
                scanners_plannedscan
            WHERE
                requested_at_when >= '%(when)s'
            GROUP BY
                scanner, activity, state
            """ % {'when': when}

    cursor = connection.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()

    overview = []
    for row in rows:
        overview.append({
            'scanner': row[0],
            'activity': row[1],
            'state': row[2],
            'amount': row[3]
        })

    return overview


def reset():
    PlannedScan.objects.all().delete()


def pickup(activity: str, scanner: str, amount: int = 10) -> List[Url]:
    """
    Amount should not be too high: then this loses it's power and make scans invisible again. But it helps
    with faster scanning as fewer queries are needed.

    param: activity: discovery, verify or scan
    param: scanner: the name of the scanner
    amount: the amount of plannedscans to pick up
    """

    scans = PlannedScan.objects.all().filter(activity=activity, scanner=scanner, state="requested")[0:amount]
    for scan in scans:
        # todo: should there be a state log? Probably.
        scan.state = "picked_up"
        scan.save()

    urls = [scan.url for scan in scans]
    log.debug(f"Picked up {len(urls)} to {activity} with {scanner}.")
    return urls


def request(activity: str, scanner: str, urls: List[Url]):
    # should it be deduplicated? i mean: if there already is a specific planned scan, it doesn't
    # need to be created again: that would just be more work. Think so, otherwise the finish and start will
    # mix for different scans. So we can't do bulk inserts, but we can do better state logging

    for url in urls:
        if already_requested(activity, scanner, url):
            log.warning(f"Already registered: {activity} on {scanner} for {url}.")
            continue

        ps = PlannedScan()
        ps.activity = activity
        ps.scanner = scanner
        ps.url = url
        ps.state = "requested"
        ps.requested_at_when = datetime.now(pytz.utc)
        ps.save()

    log.debug(f"Requested {activity} with {scanner} on {len(urls)} urls.")


def already_requested(activity: str, scanner: str, url: Url):
    return PlannedScan.objects.all().filter(
        activity=activity, scanner=scanner, url=url, state__in=["requested", "picked_up"]
    ).exists()


@app.task(queue='storage')
def finish(activity: str, scanner: str, url: Url):
    set_scan_state(activity, scanner, url, "finished")


def set_scan_state(activity: str, scanner: str, url: Url, state="finished"):
    oldest_scan = PlannedScan.objects.all().filter(
        activity=activity, scanner=scanner, url=url, state="picked_up"
    ).first()
    if oldest_scan:
        oldest_scan.state = state
        oldest_scan.finished_at_when = datetime.now(pytz.utc)
        oldest_scan.save()

        log.debug(f"Altered planned scan state for {url}. Changing it to {activity} with {scanner}.")
    else:
        log.debug(f"No planned scan found for {url}. Ignored.")


@app.task(queue='storage')
def finish_multiple(activity: str, scanner: str, urls: List[Url]):
    for url in urls:
        finish(activity, scanner, url)


def retrieve_endpoints_from_urls(
    urls: List[Url],
    protocols: List[str] = None,
    ports: List[int] = None,
    ip_versions: List[int] = None
) -> List[Endpoint]:
    """
    Given this approach reduces all scans to urls, and some scans require endpoints.

    """
    endpoints = []

    ep_querysets = Endpoint.objects.all().filter(url__in=urls)

    if protocols:
        ep_querysets = ep_querysets.filter(protocol__in=protocols)

    if ports:
        ep_querysets = ep_querysets.filter(port__in=ports)

    if ip_versions:
        ep_querysets = ep_querysets.filter(ip_version__in=ip_versions)

    ep_querysets = ep_querysets.only("id", "port", "ip_version", "url__url")
    endpoints += list(ep_querysets)

    return endpoints
