from collections import defaultdict
from typing import Dict, Any, List

from django.db.models import Prefetch

from websecmap.app import log
from websecmap.reporting.models import ScanPolicy
from websecmap.reporting.time_cache import cache_set, cache_get
from websecmap.scanners.models import Scanner, ScanSubject, ScanType


def get_scanners_for_backend():
    # get scanner config from the database, molds them to the format used in the software,
    # which has all kinds of optimizations
    results = []
    # todo: prefetch scan_types to improve speed of loading
    scanners = Scanner.objects.all().prefetch_related(
        Prefetch('plannable_activities', to_attr='plannable'),
        Prefetch('creates_scan_types', to_attr='created_scan_types'),
    )
    for scanner in scanners:
        endpoint_scan_types = []
        url_scan_types = []

        planable_activities = [item.name for item in scanner.plannable]
        if scanner.to == ScanSubject.ENDPOINT:
            endpoint_scan_types = [item.name for item in scanner.created_scan_types]
        if scanner.to == ScanSubject.URL:
            url_scan_types = [item.name for item in scanner.created_scan_types]

        # make sure this maps to the classes correctly, so use "plannable_activities" instead of with spaces
        scanner_data = {
            "id": scanner.id,
            "name": scanner.name,
            "python_name": scanner.python_name,
            "description": scanner.description,
            "rate_limit": scanner.rate_limit,
            "to": scanner.to,
            "plannable_activities": sorted(planable_activities),
            "creates_endpoint_scan_types": sorted(endpoint_scan_types),
            "creates_url_scan_types": sorted(url_scan_types),
            "can_scan_endpoints": "scan" in planable_activities and scanner.to == ScanSubject.ENDPOINT,
            "can_discover_endpoints": "discover" in planable_activities and scanner.to == ScanSubject.ENDPOINT,
            "can_verify_endpoints": "verify" in planable_activities and scanner.to == ScanSubject.ENDPOINT,
            "can_scan_urls": "scan" in planable_activities and scanner.to == ScanSubject.URL,
            "can_discover_urls": "discover" in planable_activities and scanner.to == ScanSubject.URL,
            "can_verify_urls": "verify" in planable_activities and scanner.to == ScanSubject.URL,
            "needs_results_from": [scanner.needs_results_from.id] if scanner.needs_results_from else [],
        }
        results.append(scanner_data)

    return results


def scan_type_policy_to_text(policy: ScanPolicy) -> List[str]:
    texts = []

    if policy.high:
        texts.append("high")
    if policy.medium:
        texts.append("medium")
    if policy.low:
        texts.append("low")
    if policy.ok:
        texts.append("ok")

    return texts


def get_impacts_per_scan_type() -> Dict[str, List[str]]:
    # to speed up stuff....
    policies = defaultdict(list)

    for policy in ScanPolicy.objects.all().only("scan_type", "high", "medium", "low", "ok"):
        # remove redundant items
        if policy not in policies[policy.scan_type]:
            policies[policy.scan_type] += scan_type_policy_to_text(policy)

    return policies


def get_scanners_for_frontend(all_settings):
    # frontend scanners have details about documentation

    possible_relevant_impacts = get_impacts_per_scan_type()

    results = {}
    scantypes = (
        ScanType.objects.all()
        .only("id", "name")
        .order_by("display_order")
        .prefetch_related(
            Prefetch("category", to_attr="cat"),
            Prefetch("documentation_links", to_attr="doc"),
            Prefetch("second_opinion_links", to_attr="sec"),
        )
    )

    metadata = get_backend_scanmetadata()

    for scan_type in scantypes:
        # the relevant impacts are not directly coupled to the scanners yet, this might give some small management
        # issues. For now it's fine. A future version can solve this.
        # you need all of them...

        if scan_type.name not in metadata["scan_types_in_frontend"]:
            continue

        data = {
            "name": scan_type.name,
            "id": scan_type.id,
            "category": [item.name for item in scan_type.cat],
            "relevant impacts": possible_relevant_impacts[scan_type.name],
            "documentation links": [{"name": item.friendly_name, "url": item.url} for item in scan_type.doc],
            "second opinion links": [{"name": item.friendly_name, "url": item.url} for item in scan_type.sec],
        }

        results[scan_type.name] = data

    return results


def get_backend_scanmetadata():
    # The metadata is used everywhere and was a set of constants: thus it was always assumed they where super fast
    # and present. Now they are database values. As such they might change, but we don't want to re-fetch them
    # for every call, but lru_cache is also a no go as that is per-boot and causes other complex issues during
    # tests when it's called and the result was empty (it will stay empty)
    # Hence using a 10 minute cache on the value prevents the need for reboots all the time:
    data = cache_get("backend_scanmetadata")
    if data:
        return data

    # no data? that's weird? don't store it so nothing useless is stored in cache
    data = _get_backend_scanmetadata()
    # no data in database it seems, this happens during running the entire test suite at some point, and the
    # cache is thus incorrect and will crash all other tests...
    if not data['scanners']:
        return data

    data = cache_set("backend_scanmetadata", data)
    return data


# @lru_cache(maxsize=128, typed=False)
def _get_backend_scanmetadata():
    # These used to be constants like SCANNERS, ALL SCAN TYPES, SCANNERS_BY_NAME etc, but these are now configured
    # and stored in the database. So... not constant
    # To avoid hits on the database for this usage an LRU cache is used. When scan metadata is changed, the app
    # should re-load:
    # Todo: cache the data for 10 minutes or so like the constance cache...? This might have side effects.

    scanners = get_scanners_for_backend()

    endpoint_scan_types = []
    url_scan_types = []
    for scanner in scanners:
        endpoint_scan_types = list(set(endpoint_scan_types + scanner["creates_endpoint_scan_types"]))
        url_scan_types = list(set(url_scan_types + scanner["creates_url_scan_types"]))

    all_scan_types = url_scan_types + endpoint_scan_types

    # convert endpoint scan types to scanners, so we know what endpoint scan type belongs to what scanner
    scan_types_to_scanner = {}
    for scanner in scanners:
        for scan_type in scanner["creates_endpoint_scan_types"]:
            scan_types_to_scanner[scan_type] = scanner

        for scan_type in scanner["creates_url_scan_types"]:
            scan_types_to_scanner[scan_type] = scanner

    scanners_by_id = {scanner["id"]: scanner for scanner in scanners}

    # It's impossible to know what ID you have as a scanner. We _CAN_ force it but we wont as it will become a mess.
    scanners_by_python_name: Dict[str, Any] = {scanner["python_name"]: scanner for scanner in scanners}

    scanners_by_scan_type: Dict[str, Any] = {}
    for scanner in scanners:
        for epst in scanner["creates_endpoint_scan_types"]:
            scanners_by_scan_type[epst] = scanner
        for epst in scanner["creates_url_scan_types"]:
            scanners_by_scan_type[epst] = scanner

    # todo: add config options for each of the scans defined above, include them in constance.
    # todo: check these config options dynamically at the right moments, so to reduce maintenance.

    scan_types_in_report = list(ScanType.objects.all().filter(include_in_report=True).values_list("name", flat=True))
    scan_types_in_frontend = list(ScanType.objects.all().filter(show_in_frontend=True).values_list("name", flat=True))

    published_url_scan_types = [scan_type for scan_type in scan_types_in_report if scan_type in url_scan_types]
    published_endpoint_scan_types = [
        scan_type for scan_type in scan_types_in_report if scan_type in endpoint_scan_types
    ]

    metadata = {
        "scanners": scanners,
        "all_scan_types": all_scan_types,
        "scanners_by_id": scanners_by_id,
        "scanners_by_python_name": scanners_by_python_name,
        "scanners_by_scan_type": scanners_by_scan_type,
        "scan_types_to_scanner": scan_types_to_scanner,
        "url_scan_types": url_scan_types,
        "endpoint_scan_types": endpoint_scan_types,
        "published_scan_types": scan_types_in_report,
        "published_url_scan_types": published_url_scan_types,
        "published_endpoint_scan_types": published_endpoint_scan_types,
        "scan_types_in_frontend": scan_types_in_frontend,
    }

    # log.error(json.dumps(metadata, indent=2))

    return metadata
