import json
import os
from collections import defaultdict
from logging import getLogger

from constance import config

from websecmap.map.report import PUBLISHED_ENDPOINT_SCAN_TYPES, PUBLISHED_URL_SCAN_TYPES
from websecmap.reporting.severity import get_severity
from websecmap.scanners.models import Endpoint, EndpointGenericScan

log = getLogger(__package__)


def report_impact_to_commandline():
    print(json.dumps(calculate_impact(), indent=2))


# todo: add DNSSEC(!)


def calculate_impact():
    """
    Based on scans: the first and the last measurement, calculates numbers on how much has changed. It takes
    into account how much endpoints / urls are deleted. This script is slow, but also simple. This simplicty
    makes it easy to understand and maintain.
    It does not understand organizations and other hierarchy (yet).
    https://stackoverflow.com/questions/59006602/dyld-library-not-loaded-usr-local-opt-openssl-lib-libssl-1-0-0-dylib
    Impact:
    {
        "metadata": {
            "first scan": date,
            "newest scan": date,
            "recorded changes": amount,
        },
        "scan_types": {
            "tls": {
                // endpoint-based
                // first scan:
                "high": {
                    // last scan:
                    "high": 0,
                    "medium": 0,
                    "low": 0,
                    "good": 0,
                },
                "medium": {
                    ...
                },
                ...
            }
        }
    }
    """
    impact = {
        "metadata": {
            # how many changes are recorded for these endpoints
            "recorded_changes": 0,
            # how many things have an "updated" state, gives insight of the amount of data points on the map
            "amount_of_current_scans": 0,
            # the endpoints involved in the current set
            "endpoints": 0,
            "changes": 0,
            "improvements": 0,
            "degradations": 0,
        },
        "scan_types": defaultdict(dict),
        "total": {
            "high": {"high": 0, "medium": 0, "low": 0, "good": 0},
            "medium": {"high": 0, "medium": 0, "low": 0, "good": 0},
            "low": {"high": 0, "medium": 0, "low": 0, "good": 0},
            "good": {"high": 0, "medium": 0, "low": 0, "good": 0},
        },
    }
    published_scans = PUBLISHED_ENDPOINT_SCAN_TYPES + PUBLISHED_URL_SCAN_TYPES
    # we'll ignore explanations
    for scan_type in published_scans:
        impact["scan_types"][scan_type] = {
            "high": {"high": 0, "medium": 0, "low": 0, "good": 0},
            "medium": {"high": 0, "medium": 0, "low": 0, "good": 0},
            "low": {"high": 0, "medium": 0, "low": 0, "good": 0},
            "good": {"high": 0, "medium": 0, "low": 0, "good": 0},
        }
    # count down id's, so there is some feeling on how long it will take.
    log.debug(f"Calculating impact for country: {config.PROJECT_COUNTRY}.")
    # do not take endpoints that are "switching" on and off, only alive endpoints and urls
    all_endpoints = (
        Endpoint.objects.all()
        .filter(
            is_dead=False,
            url__is_dead=False,
            url__not_resolvable=False,
            url__organization__country=config.PROJECT_COUNTRY,
            url__organization__type__name="municipality",
        )
        .only("id")
        .order_by("-id")
    )
    number_of_changes = (
        EndpointGenericScan.objects.all()
        .filter(
            endpoint__is_dead=False,
            endpoint__url__is_dead=False,
            endpoint__url__not_resolvable=False,
            endpoint__url__organization__country=config.PROJECT_COUNTRY,
            endpoint__url__organization__type__name="municipality",
        )
        .only("id")
    )
    number_of_unique_changes = len(list(set(number_of_changes)))
    impact["metadata"]["recorded_changes"] = number_of_unique_changes
    number_of_current_scans = (
        EndpointGenericScan.objects.all()
        .filter(
            endpoint__is_dead=False,
            endpoint__url__is_dead=False,
            endpoint__url__not_resolvable=False,
            endpoint__url__organization__country=config.PROJECT_COUNTRY,
            endpoint__url__organization__type__name="municipality",
            is_the_latest_scan=True,
        )
        .only("id")
    )
    unique_number_of_current_scans = len(list(set(number_of_current_scans)))
    impact["metadata"]["amount_of_current_scans"] = unique_number_of_current_scans
    # duplication because some urls are shared multiple times over organizations, for example rijksoverheid.nl
    all_endpoints = list(set(all_endpoints))
    amount_of_endpoints = len(all_endpoints)
    impact["metadata"]["endpoints"] = amount_of_endpoints
    for index, endpoint in enumerate(all_endpoints):
        # log.debug(f"Endpoint {endpoint.id}")
        for scan_type in published_scans:
            # note that the "last" scan is the "oldest" scan (by id). The first scan is the newest.
            first_scan = EndpointGenericScan.objects.all().filter(endpoint=endpoint, type=scan_type).last()
            # possible that this scan type was not available for this endpoint:
            if not first_scan:
                continue
            last_scan = EndpointGenericScan.objects.all().filter(endpoint=endpoint, type=scan_type).first()
            # fully possible the first and last scan are the same. This does not show impact, skip it as it
            # only creates double numbers and total amounts:
            if first_scan == last_scan:
                continue
            severity_first = get_severity(first_scan)
            severity_last = get_severity(last_scan)
            # we also don't need to see the same severity, as nothing practically changed
            if severity_first == severity_last:
                continue
            impact_first = get_impact(severity_first)
            impact_last = get_impact(severity_last)
            if impact_first == impact_last:
                continue
            # log.debug(f"Adding 1 to: {scan_type}, {get_impact(severity_first)}, {get_impact(severity_last)}")
            # print(f"scan_type {scan_type} on endpoint {endpoint.id} "
            #       f"{'improved' if is_improved(impact_first, impact_last) else 'degraded'} from "
            #       f"{impact_first} to {impact_last}.")
            impact["scan_types"][scan_type][impact_first][impact_last] += 1
            impact["metadata"]["changes"] += 1
            if is_improved(impact_first, impact_last):
                impact["metadata"]["improvements"] += 1
            else:
                impact["metadata"]["degradations"] += 1
        # also shows on the first round, with the first analysis, so the first round is not all 0's:
        if index % 1000 == 0:
            os.system("clear")
            print(f"{round(index/amount_of_endpoints, 2) * 100}% = {index}/{amount_of_endpoints}.")
            print(json.dumps(impact, indent=2))
    # now create a total:
    gradations = ["high", "medium", "low", "good"]
    for scan_type in published_scans:
        for gradation in gradations:
            for subgradations in gradations:
                impact["total"][gradation][subgradations] += impact["scan_types"][scan_type][gradation][subgradations]
    return impact


def get_impact(severity):
    if severity["is_explained"]:
        return "good"
    return "high" if severity["high"] else "medium" if severity["medium"] else "low" if severity["low"] else "good"


def is_improved(first_scan, last_scan):
    if first_scan == "high":
        return True if last_scan in ["medium", "low", "good"] else False
    if first_scan == "medium":
        return True if last_scan in ["low", "good"] else False
    if first_scan == "low":
        return True if last_scan in ["good"] else False
    if first_scan == "good" and last_scan != "good":
        return False
    else:
        return True
