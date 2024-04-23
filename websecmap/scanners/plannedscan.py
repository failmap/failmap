import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

import dateutil.parser
from django.db import connection
from django.db.models import Prefetch
from statshog.defaults.django import statsd

from websecmap.app.constance import constance_cached_value
from websecmap.celery import app
from websecmap.map.logic.map_health import get_outdated_ratings
from websecmap.map.map_configs import filter_map_configs
from websecmap.organizations.models import Organization, Url
from websecmap.scanners.models import (
    Activity,
    Endpoint,
    EndpointGenericScan,
    FollowUpScan,
    PlannedScan,
    PlannedScanLog,
    PlannedScanStatistic,
    Scanner,
    State,
)
from websecmap.scanners.scanmetadata import get_backend_scanmetadata

log = logging.getLogger(__name__)


@app.task(queue="storage", ignore_result=True)
def store_progress():
    """
    Runs every N minutes (periodic task) and stores the latest calculated progress in the db.
    """
    metadata = get_backend_scanmetadata()

    progress = calculate_progress()
    pss = PlannedScanStatistic()
    pss.at_when = datetime.now(timezone.utc)
    pss.data = progress
    pss.save()

    # Also send it to statsd for nicer metrics:
    for row in progress:
        activity = Activity(row["activity"]).label
        scanner = metadata["scanners_by_id"].get(row["scanner"], {"python_name": "unknown"})["python_name"]
        state = State(row["state"]).label

        statsd.gauge("scan_progress", row["amount"], tags={"state": state, "scanner": scanner, "activity": activity})


def get_latest_progress():
    pss = PlannedScanStatistic.objects.last()
    return pss.data if pss else {}


def calculate_progress() -> List[Dict[str, int]]:
    """
    Retrieves the progress of all scans in the past 7 days. Will show how many are requested and how many
    are at what state.

    This routine is as simple and fast as it gets. The consumer will have to iterated and aggregate where needed.
    """

    # i'm _DONE_ with the obscuring of group_by and counts using terrible abstractions.
    # so here is a raw query that just works on all databases and is trivially simple to understand.
    sql = """SELECT
                scanner_id, activity, state, count(id) as amount
            FROM
                scanners_plannedscan
            GROUP BY
                scanner_id, activity, state
            """

    cursor = connection.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()

    # when there are 0 records, there is of course no row created. But there might have been in the past.
    overview: List[Dict[str, int]] = [
        {"scanner": row[0], "activity": row[1], "state": row[2], "amount": row[3]} for row in rows
    ]

    for scanner in Scanner.objects.all():
        scanner_id = scanner.id

        if scanner_has_finished_tasks(scanner_id, overview):
            # scan, discover and verify, not all scanners will perform all three.
            for activity in activities_from_finished_tasks(scanner_id, overview):
                # unknown error and timeout are ignored because they are not used
                for state in [State["requested"].value, State["picked_up"].value, State["finished"].value]:
                    # it's not in the overview when we're here, so add it:
                    if not already_in_overview(overview, scanner_id, activity, state):
                        overview.append({"scanner": scanner_id, "activity": activity, "state": state, "amount": 0})

    # Sort by scanner for easier human comprehension.
    overview = sorted(overview, key=lambda o: (o["scanner"], o["activity"], o["state"]))

    return overview


def already_in_overview(overview, scanner, activity, state):
    return sum(row["scanner"] == scanner and row["activity"] == activity and row["state"] == state for row in overview)


def scanner_has_finished_tasks(scanner_id, overview):
    return activities_from_finished_tasks(scanner_id, overview)


def activities_from_finished_tasks(scanner_id, overview):
    return [
        row["activity"] for row in overview if row["scanner"] == scanner_id and row["state"] == State["finished"].value
    ]


def reset():
    PlannedScan.objects.all().delete()


@app.task(queue="storage", ignore_result=True)
def force_retry():
    # just retry everything that is picked up now:
    PlannedScan.objects.all().filter(state=State["picked_up"].value).update(state=State["requested"].value)


@app.task(queue="kickoff", ignore_result=True)
def retry():
    """
    When something is picked up, but not finished in a day, just retry. Something went wrong.

    This might result in a bunch of the same things being attempted over and over because they are never
    finished. Those things are nice investigation subjects. All scans should finish (or error).

    internet_nl_mail and internet_nl_web have their own retry methods, they should NOT be retried after four hours
    but after days! So plan them after a large amount of minutes! Such as 1440 minutes (a day) or triple that...
    """

    for scanner in Scanner.objects.all():
        scan_timeout = datetime.now(timezone.utc) - timedelta(minutes=scanner.task_pickup_timeout_in_minutes)
        updated = (
            PlannedScan.objects.all()
            .filter(
                state=State["picked_up"].value,
                last_state_change_at__lte=scan_timeout,
                scanner=scanner,
                # returns number of affected rows
            )
            .update(state=State["requested"].value)
        )
        log.debug("Retried %s planned scans for %s", updated, scanner.python_name)


def pickup(activity: str, scanner: str, amount: int = 10) -> List[Url]:
    """
    Amount should not be too high: then this loses it's power and make scans invisible again. But it helps
    with faster scanning as fewer queries are needed.

    param: activity: discovery, verify or scan
    param: scanner: the name of the scanner
    amount: the amount of plannedscans to pick up
    """

    metadata = get_backend_scanmetadata()

    python_scanner = metadata["scanners_by_python_name"].get(scanner, None)
    if not python_scanner:
        log.error(f"Scan requested for {scanner}, but no such scanner registered in metadata database. Not picked up.")
        return []

    # Do not pickup more if there are already 500 items picked up. Having more than 500 items picked up means
    # a throughput error. If you want to go faster you can always increase the frequency of things being picked up
    # as long as they are handled faster.
    already_picked_up = (
        PlannedScan.objects.all()
        .filter(activity=Activity[activity].value, scanner=python_scanner["id"], state=State["picked_up"].value)
        .count()
    )

    max_picked_up_simultaneously = python_scanner["rate_limit"]

    if already_picked_up >= max_picked_up_simultaneously:
        return []

    # Limit the total amount of picked up to being maximum of MAX_PICKED_UP_SIMULTANEOUSLY.
    headroom = max_picked_up_simultaneously - already_picked_up
    amount = min(amount, headroom)
    log.debug("Picking up maximum %s of total %s free slots.", amount, headroom)

    # oldest first, so ascending dates.-> removed because that makes picking up very slow and complex.
    # whatever is requested should just be handled asap and the things that are requestes should just be empy
    # at the end of the day. So no .order_by("requested_at_when")
    scans = PlannedScan.objects.all().filter(
        activity=Activity[activity].value, scanner=python_scanner["id"], state=State["requested"].value
    )[:amount]

    # cannot update once a slice has been taken
    for scan in scans:
        # pick up multiple at the same time. This might skew the numbers a bit if there are a few of the
        # same url. So statistically there might be 10 of the same url and the same state that are being picked
        # up but in terms of scanning only one scan is carried out and only one time results are stored.
        # So planning scans multiple times is ok but don't do that too much as it will skew the numbers.
        set_scan_state(
            activity=activity,
            scanner_id=python_scanner["id"],
            url_id=scan.url,
            from_state="requested",
            to_state="picked_up",
            scanner_name=scanner,
        )

        # here is the old code to only pick up one scan.
        # scan.state = State["picked_up"].value
        # scan.last_state_change_at = datetime.now(timezone.utc)
        # scan.save()
        log_planned_scan_action(activity=activity, scanner=scanner, url=scan.url, state="picked_up")

    urls = []
    for scan in scans:
        # There are plannedscans on http without an url reference. The url show up blank in the admin, even when
        # there is cascading deletion. So there might be a database error somewhere.
        # scan still exists (weirdly enough). Even if there is an on delete cascade. We see that in issue 2424378050.
        try:
            # Use this debug message to retrieve the Url.DoesNotExist as django has to query the ID.
            log.debug("Picking up scan %s with url id: %s.", scan.id, scan.url.id)
            urls.append(scan.url)
        except Url.DoesNotExist:
            # Delete this scan as the url id cannot be found, so it cannot be finished.
            log.error("Deleting a scan without an url. The scan will be deleted.", extra={"scan_id": scan.id})
            scan.delete()
            log_planned_scan_action(activity=activity, scanner=scanner, url=scan.url, state="scan_deleted_no_url")

    log.debug("Picked up %s to %s with %s.", len(urls), activity, scanner)
    statsd.incr("scan_planned", len(urls), tags={"state": "pickup", "scanner": scanner, "activity": activity})
    return urls


def request(activity: str, scanner: str, urls: List[int], origin: str = ""):
    # should it be deduplicated? i mean: if there already is a specific planned scan, it doesn't
    # need to be created again: that would just be more work. Think so, otherwise the finish and start will
    # mix for different scans. So we can't do bulk inserts, but we can do better state logging
    metadata = get_backend_scanmetadata()
    log.debug("Requested %s with %s on %s urls.", activity, scanner, len(urls))

    python_scanner = metadata["scanners_by_python_name"].get(scanner, None)
    if not python_scanner:
        log.error(f"Scan requested for {scanner}, but no such scanner registered in metadata database. Not requested.")
        return

    scanner_obj = Scanner.objects.get(pk=python_scanner["id"])

    activity_obj = Activity[activity].value
    state_obj = State["requested"].value

    for url in urls:
        # we've removed already requestsed as it creates a lookup for every new requested scan.
        #
        #  instead of this we're just adding the new scan request because it got requested.
        #  and when finishing a scan we're finishing all unfinished ones. This prevents extra lookups and thus
        #  speeds up handling of the queue. There could be millions of scans already finished etc...
        # if already_requested(activity, python_scanner["id"], url):
        #     statsd.incr("scan_planned", tags={"state": "duplicate_request", "scanner": scanner, "activity": activity})
        #     log.debug("Already registered: %s on %s for %s.", activity, scanner, url)
        #     continue

        now = datetime.now(timezone.utc)

        planned_scan = PlannedScan()
        planned_scan.activity = activity_obj
        planned_scan.scanner = scanner_obj
        planned_scan.url = url
        planned_scan.state = state_obj
        planned_scan.last_state_change_at = now
        planned_scan.origin = origin
        # To use the index on requested_at_when times are reduced to whole hours.
        # This is sane enough to allow tons of scans per day still, but the creation
        # of status reports is much faster. Still gives an idea of how many scans are made.
        # The minutes are rounded to every 10 minutes. So there is still a sense of progress and use the index
        discard = timedelta(minutes=now.minute % 10, seconds=now.second, microseconds=now.microsecond)
        planned_scan.requested_at_when = now - discard
        planned_scan.save()
        log_planned_scan_action(activity=activity, scanner=scanner, url=url, state="requested", origin=origin)
        statsd.incr("scan_planned", tags={"state": "request", "scanner": scanner, "activity": activity})


def log_planned_scan_action(activity: str, scanner: str, url: int, state: str = "", origin: str = ""):
    # logging all actions to the database is write intensive and slows things down by a bit.
    # it quickly accumulates into a million a day and we're not even looking at that table in production anymore.
    if constance_cached_value("SCANNER_LOG_PLANNED_SCANS") is False:
        return

    if isinstance(url, Url):
        # might be an n+1
        url = url.url

    if isinstance(scanner, Scanner):
        scanner = scanner.id

    log_item = PlannedScanLog()
    log_item.line = f"Url: {url}, Activity: {activity}, Scanner: {scanner}, State: {state}, Origin: {origin}"[:255]
    log_item.save()


def already_requested(activity: str, scanner: int, url_id: int):
    return (
        PlannedScan.objects.all()
        .filter(
            activity=Activity[activity].value,
            scanner=scanner,
            url=url_id,
            state__in=[State["requested"].value, State["picked_up"].value],
        )
        .exists()
    )


@app.task(queue="storage", ignore_result=True)
def finish(activity: str, scanner: str, url_id: int):
    metadata = get_backend_scanmetadata()
    py_scanner = metadata["scanners_by_python_name"].get(scanner, None)
    if not py_scanner:
        log_planned_scan_action(activity=activity, scanner=scanner, url=url_id, state="finished (no scanner)")
        log.debug(f"Scanner {py_scanner} was not found, ignoring.")
        return

    set_scan_state(
        activity, py_scanner["id"], url_id, from_state="picked_up", to_state="finished", scanner_name=scanner
    )
    statsd.incr("scan_planned", tags={"state": "finished", "scanner": scanner, "activity": activity})


def set_scan_state(
    activity: str, scanner_id: int, url_id: int, from_state="picked_up", to_state="finished", scanner_name=""
):
    # Instead of moving just one, move all that have a certain state. This is done because we do not want to check
    # anymore if something has been added. In case there are 10 scans for the same stuff, you only need one actual
    # scan to finish all the ones that are requested.
    current_scans = PlannedScan.objects.all().filter(
        activity=Activity[activity].value,
        scanner=scanner_id,
        url=url_id,
        state=State[from_state].value,
    )
    if not current_scans:
        log.debug("No planned scan found for %s. Ignored.", url_id)
        log_planned_scan_action(activity=activity, scanner=scanner_name, url=url_id, state="finished (unplanned)")
        return

    if current_scans.count() > 1:
        log.warning(
            "Progressiong %s %s %s scans to %s. Some tasks have been requested " "before the old ones where done.",
            current_scans.count(),
            activity,
            scanner_name,
            to_state,
        )

    for oldest_scan in current_scans:
        oldest_scan.state = State[to_state].value
        oldest_scan.last_state_change_at = datetime.now(timezone.utc)

        if to_state == "finished":
            oldest_scan.finished_at_when = datetime.now(timezone.utc)

        oldest_scan.save()
        log_planned_scan_action(activity=activity, scanner=scanner_name, url=url_id, state="finished")

        log.debug("Altered planned scan state for %s. Changing it to %s with %s.", url_id, activity, scanner_id)


@app.task(queue="storage", ignore_result=True)
def finish_multiple(activity: str, scanner: str, urls: List[int]):
    for url in urls:
        finish(activity, scanner, url)


def retrieve_endpoints_from_urls(
    urls: List[Url],
    protocols: List[str] = None,
    ports: List[int] = None,
    ip_versions: List[int] = None,
    is_dead: bool = False,
) -> Tuple[List[Endpoint], List[int]]:
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

    # endpoints could be deleted, removed, dead, whatever, in that case the planned scan has to be
    # deleted as well. We have to know what urls are not in the set we requested, so those urls can
    # be removed from the planned scans.
    urls_without_endpoints = list({url.id for url in urls} - {ep.url.id for ep in endpoints})

    return endpoints, urls_without_endpoints


@app.task(queue="kickoff")
def websecmap_plan_outdated_scans():
    # one without parameters
    metadata = get_backend_scanmetadata()

    return plan_outdated_scans(metadata["published_scan_types"])


@app.task(queue="database")
def websecmap_list_outdated():
    # one without parameters
    metadata = get_backend_scanmetadata()
    return list_outdated(metadata["published_scan_types"])


@app.task(queue="storage", ignore_result=True)
def list_outdated(published_scan_types):
    metadata = get_backend_scanmetadata()

    for map_configuration in filter_map_configs():
        print(f"Outdated items for {map_configuration['country']}/{map_configuration['organization_type__name']}:")
        organizations_on_map = Organization.objects.all().filter(
            country=map_configuration["country"], layers=map_configuration["organization_type"]
        )
        # Outdated is earlier than the map_health says something is outdated. Otherwise we're always
        # one day behind with scans, and thus is always something outdated.
        outdated = get_outdated_ratings(organizations_on_map, 24 * 5)
        relevant_outdated = [item for item in outdated if item.get("scan_type", "unknown") in published_scan_types]
        plan = []
        for outdated_result in relevant_outdated:
            scanner = metadata["scan_types_to_scanner"][outdated_result["scan_type"]]
            plan.append(
                {
                    "scanner": scanner["id"],
                    "url": outdated_result["url"],
                    "activity": Activity["scan"].value,
                    "last_scan": outdated_result["last_scan"],
                    "scan": outdated_result["scan"],
                }
            )
        plan = deduplicate_plan(plan)

        # update the dates to match:
        for activity in plan:
            activity["last_scan"] = dateutil.parser.isoparse(activity["last_scan"])

        plan = sorted(plan, key=lambda mplan: mplan["last_scan"])
        print(f" For a total of {len(plan)} items:")
        print("-------------------------------------------------------------------------------------------------------")
        print(f"{'Last scan':22} {'Scan':9} {'Activity':10} {'Scanner':30} {'Url':60}")
        print("-------------------------------------------------------------------------------------------------------")

        for item in plan:
            print(
                f"{str(item['last_scan'].strftime('%Y-%m-%d %H:%M:%S')):22} {item['scan']:9} "
                f"{item['activity']:10} {item['scanner']:30} {item['url']:60}"
            )


def deduplicate_plan(planned_items):
    hashed_items = []
    clean_plan = []
    for item in planned_items:
        hashed_item = f"{item['activity']} {item['scanner']} {item['url']}"

        if hashed_item not in hashed_items:
            hashed_items.append(hashed_item)
            clean_plan.append(item)

    return clean_plan


@app.task(queue="kickoff", ignore_result=True)
def plan_outdated_scans(published_scan_types):
    metadata = get_backend_scanmetadata()

    for map_configuration in filter_map_configs():
        log.debug("Retrieving outdated scans from config: %s.", map_configuration)

        organizations_on_map = Organization.objects.all().filter(
            country=map_configuration["country"], layers=map_configuration["organization_type"]
        )

        log.debug("There are %s organizations on this map.", len(organizations_on_map))

        # Outdated is earlier than the map_health says something is outdated. Otherwise we're always
        # one day behind with scans, and thus is always something outdated.
        outdated = get_outdated_ratings(organizations_on_map, 24 * 5)
        relevant_outdated = [item for item in outdated if item.get("scan_type", "unknown") in published_scan_types]

        # plan scans for outdated results:
        plan = []
        for outdated_result in relevant_outdated:
            scanner = metadata["scan_types_to_scanner"][outdated_result["scan_type"]]
            plan.append(
                {
                    "scanner": scanner["python_name"],
                    "url": outdated_result["url"],
                    "activity": "scan",
                }
            )

            # see if there are requirements for verification or discovery from other scanners:
            # log.debug(f"There are {len(scanner['needs results from'])} underlaying scanners.")
            for underlaying_scanner in scanner["needs_results_from"]:
                underlaying_scanner_details = metadata["scanners_by_id"][underlaying_scanner]

                if any(
                    [
                        underlaying_scanner_details["can_discover_endpoints"],
                        underlaying_scanner_details["can_discover_urls"],
                    ]
                ):
                    plan.append(
                        {
                            "scanner": underlaying_scanner_details["python_name"],
                            "url": outdated_result["url"],
                            "activity": "discover",
                        }
                    )
                if any(
                    [
                        underlaying_scanner_details["can_verify_endpoints"],
                        underlaying_scanner_details["can_verify_urls"],
                    ]
                ):
                    plan.append(
                        {
                            "scanner": underlaying_scanner_details["python_name"],
                            "url": outdated_result["url"],
                            "activity": "verify",
                        }
                    )

        # there can be many duplicate tasks, especially when there are multiple scan results from a single scanner.
        clean_plan = deduplicate_plan(plan)

        # make sure the urls are actual urls. Only plan for alive urls anyway.
        clean_plan_with_urls = []
        for item in clean_plan:
            url = Url.objects.all().filter(url=item["url"], is_dead=False, not_resolvable=False).first()
            if url:
                item["url"] = url
                clean_plan_with_urls.append(item)

        # and finally, plan it...
        for item in clean_plan_with_urls:
            request(item["activity"], item["scanner"], [item["url"]])

        log.debug("Planned %s scans / verify and discovery tasks.", len(clean_plan_with_urls))


# todo: the storage queue might be too busy for this... should become a new queue...
@app.task(queue="followupscan", ignore_result=True)
def plan_follow_up_scans(**kwargs):
    """
    Based on the conclusion a new scan is scheduled. We'll receive a ton of conclusions because a scanner can
    have multiple conclusions. But the follow up only happens on certain conclusions. It is independent if that
    conclusion is rated as high/medium/low/neutral/ok etc: that's just a setting of the scan policy.

    These follow ups are just to make certain measurements are correct or corrected.

    todo: perhaps make a dict of scan types and conclusions. What would work / be the easiest from other scanners?

    Could this be preloaded, to prevent a query after each scan? Or could we just see what new scans have been done
    in the past 10 minutes and plan scans as a result on that? This would be more efficient AND

    Run every 5 minutes and see what happened in the last 5 minutes. That prevents a lot of complexity.
    This also reduces the need to know what scanner created any result. You only need to detect the scanpolicy.

    """

    # Find all recent url/endpoint scan results
    # See if there are any that match the re-scan policy
    # request a scan for the matches
    # scanner_python_name, url_that_has_been_scanned, scan_types, conclusions_received

    amount_of_minutes_of_scan_history = 20
    if kwargs.get("in_the_last_N_minutes"):
        amount_of_minutes_of_scan_history = int(kwargs.get("amount_of_minutes_of_scan_history"))

    log.info("Adding follow up scans to results from the last %s minutes.", amount_of_minutes_of_scan_history)

    # Instead of this here is a slow and dumb implementation, which works when run every ten minutes or so

    for follow_up_scan in FollowUpScan.objects.all().prefetch_related(
        Prefetch("run_follow_up_on_any_of_these_policies", to_attr="otherpolicies")
    ):
        # are there scans in the last 10 minutes that match this policy:
        for policy in follow_up_scan.otherpolicies:
            log.info("Checking if there are follow ups for %s, %s", policy.scan_type, policy.conclusion)

            scans_matching_policy = EndpointGenericScan.objects.all().filter(
                type=policy.scan_type,
                rating=policy.conclusion,
                last_scan_moment__gt=datetime.now(timezone.utc) - timedelta(minutes=amount_of_minutes_of_scan_history),
            )

            for scan_matching_policy in scans_matching_policy:
                # Request all activities from this scanner
                # scanner = metadata["scan_types_to_scanner"].get(policy.scan_type, None)
                follow_up_scanner = follow_up_scan.follow_up_scanner

                if not follow_up_scanner:
                    log.warning(
                        "Could not find a scanner matching scan type %s, cannot add follow up scan.", policy.scan_type
                    )
                    continue

                for activity in follow_up_scanner.plannable_activities.all():
                    log.info(
                        "- Planning activity %s with scanner %s, for url %s",
                        activity.name,
                        follow_up_scanner.python_name,
                        scan_matching_policy.endpoint.url,
                    )
                    request(
                        scanner=follow_up_scanner.python_name,
                        activity=activity.name,
                        urls=[scan_matching_policy.endpoint.url],
                        origin=f"Follow up from {policy}"[:255],
                    )


def generic_retry_watcher(scanner_name: str, activity: int, minutes: int = 30):
    # Use this when the normal 48 hours is too long. Use this method until scanners / activities support their
    # own retry mechanism. This is a workaround that should disappear.
    # Since only one scan can be run at one time, a reboot of the software might mean that a currently running
    # scan is terminated. The normal 'recovery' period is 48 hours, which is WAY too long. Instead of messing
    # with the existing recovery architecture, this function measures tasks that have been running for too long and
    # resets them to requested. At that moment the next scan can be picked up. Expecting a timeout of 30 minutes.
    # which should be way than more than enough to finish a scan on a domain.

    scan_too_old = datetime.now() - timedelta(minutes=minutes)

    scanner = Scanner.objects.all().filter(python_name=scanner_name).first()
    if not scanner:
        log.error("Could not find a scanner named %s", scanner_name)
        return

    outdated_scans = PlannedScan.objects.filter(
        scanner=scanner, activity=activity, state=State.picked_up, last_state_change_at__lte=scan_too_old
    )

    if not outdated_scans:
        # happens a lot of times
        log.debug("No outdated %s discovery scans found", scanner_name)
        return

    # we could do an update, but that has no logging, which can cause confusion
    for outdated_scan in outdated_scans:
        log.debug("Setting outdated amass discovery scan to requested: %s", outdated_scan.pk)
        outdated_scan.state = State.requested
        outdated_scan.save()
