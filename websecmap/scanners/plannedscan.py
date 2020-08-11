import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytz
from django.db import connection

from websecmap.celery import app
from websecmap.map.logic.map_health import get_outdated_ratings
from websecmap.map.map_configs import filter_map_configs
from websecmap.map.report import PUBLISHED_SCAN_TYPES
from websecmap.organizations.models import Organization, Url
from websecmap.scanners import SCAN_TYPES_TO_SCANNER, SCANNERS_BY_NAME
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


@app.task(queue='storage')
def retry():
    """
    When something is picked up, but not finished in a day, just retry. Something went wrong.

    This might result in a bunch of the same things being attempted over and over because they are never
    finished. Those things are nice investigation subjects. All scans should finish (or error).

    """
    PlannedScan.objects.all().filter(
        state='picked_up',
        last_state_change_at__lte=datetime.now(pytz.utc) - timedelta(days=1)
    ).update(state='requested')


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
        scan.last_state_change_at = datetime.now(pytz.utc)
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
        ps.last_state_change_at = datetime.now(pytz.utc)
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
        oldest_scan.last_state_change_at = datetime.now(pytz.utc)
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
    ip_versions: List[int] = None,
    is_dead: bool = False
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

    ep_querysets = ep_querysets.filter(is_dead=is_dead)

    ep_querysets = ep_querysets.only("id", "port", "protocol", "ip_version", "url", "url__id", "url__url")
    endpoints += list(ep_querysets)

    return endpoints


@app.task(queue="storage")
def websecmap_plan_outdated_scans():
    # one without parameters
    return plan_outdated_scans(PUBLISHED_SCAN_TYPES)


@app.task(queue="storage")
def websecmap_list_outdated():
    # one without parameters
    return list_outdated(PUBLISHED_SCAN_TYPES)


@app.task(queue="storage")
def list_outdated(published_scan_types):
    for map_configuration in filter_map_configs():
        print(f"Outdated items for f{map_configuration}:")
        organizations_on_map = Organization.objects.all().filter(
            country=map_configuration['country'],
            type=map_configuration['organization_type']
        )
        # Outdated is earlier than the map_health says something is outdated. Otherwise we're always
        # one day behind with scans, and thus is always something outdated.
        outdated = get_outdated_ratings(organizations_on_map, 24 * 5)
        relevant_outdated = [item for item in outdated if item.get('scan_type', 'unknown') in published_scan_types]
        plan = []
        for outdated_result in relevant_outdated:
            scanner = SCAN_TYPES_TO_SCANNER[outdated_result['scan_type']]
            plan.append({
                'scanner': scanner['name'],
                'url': outdated_result['url'],
                'activity': 'scan',
            })
        plan = deduplicate_plan(plan)
        for item in plan:
            print(f"{item['activity']:20} {item['scanner']:30} {item['url']:60}")
    return


def deduplicate_plan(planned_items):
    hashed_items = []
    clean_plan = []
    for item in planned_items:
        hashed_item = f"{item['activity']} {item['scanner']} {item['url']}"

        if hashed_item not in hashed_items:
            hashed_items.append(hashed_item)
            clean_plan.append(item)

    return clean_plan


@app.task(queue="storage")
def plan_outdated_scans(published_scan_types):
    for map_configuration in filter_map_configs():
        log.debug(f"Retrieving outdated scans from config: {map_configuration}.")

        organizations_on_map = Organization.objects.all().filter(
            country=map_configuration['country'],
            type=map_configuration['organization_type']
        )

        log.debug(f"There are {len(organizations_on_map)} organizations on this map.")

        # Outdated is earlier than the map_health says something is outdated. Otherwise we're always
        # one day behind with scans, and thus is always something outdated.
        outdated = get_outdated_ratings(organizations_on_map, 24 * 5)
        relevant_outdated = [item for item in outdated if item.get('scan_type', 'unknown') in published_scan_types]

        # plan scans for outdated results:
        plan = []
        for outdated_result in relevant_outdated:
            scanner = SCAN_TYPES_TO_SCANNER[outdated_result['scan_type']]
            plan.append({
                'scanner': scanner['name'],
                'url': outdated_result['url'],
                'activity': 'scan',
            })

            # see if there are requirements for verification or discovery from other scanners:
            # log.debug(f"There are {len(scanner['needs results from'])} underlaying scanners.")
            for underlaying_scanner in scanner['needs results from']:
                underlaying_scanner_details = SCANNERS_BY_NAME[underlaying_scanner]

                if any([underlaying_scanner_details['can discover endpoints'],
                        underlaying_scanner_details['can discover urls']]):
                    plan.append({
                        'scanner': underlaying_scanner,
                        'url': outdated_result['url'],
                        'activity': 'discover'
                    })
                if any([underlaying_scanner_details['can verify endpoints'],
                        underlaying_scanner_details['can verify urls']]):
                    plan.append({
                        'scanner': underlaying_scanner,
                        'url': outdated_result['url'],
                        'activity': 'verify'
                    })

        # there can be many duplicate tasks, especially when there are multiple scan results from a single scanner.
        clean_plan = deduplicate_plan(plan)

        # make sure the urls are actual urls. Only plan for alive urls anyway.
        clean_plan_with_urls = []
        for item in clean_plan:
            url = Url.objects.all().filter(url=item['url'], is_dead=False, not_resolvable=False).first()
            if url:
                item['url'] = url
                clean_plan_with_urls.append(item)

        # and finally, plan it...
        for item in clean_plan_with_urls:
            request(item['activity'], item['scanner'], [item['url']])

        log.debug(f"Planned {len(clean_plan_with_urls)} scans / verify and discovery tasks.")
