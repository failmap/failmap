import json
from collections import defaultdict
from functools import lru_cache
from typing import Dict, Any, List

from django.db.models import Prefetch

from websecmap.app import log
from websecmap.reporting.models import ScanPolicy
from websecmap.scanners.models import Scanner, ScanSubject, ScanType


def get_scanners_for_backend():
    # get scanner config from the database, molds them to the format used in the software,
    # which has all kinds of optimizations
    results = []
    # todo: prefetch scan_types to improve speed of loading
    scanners = Scanner.objects.all()
    for scanner in scanners:
        endpoint_scan_types = []
        url_scan_types = []

        planable_activities = list(scanner.plannable_activities.all().values_list("name", flat=True))
        if scanner.to == ScanSubject.ENDPOINT:
            endpoint_scan_types = list(
                scanner.creates_scan_types.all().filter(scanner=scanner).values_list("name", flat=True)
            )
        if scanner.to == ScanSubject.URL:
            url_scan_types = list(
                scanner.creates_scan_types.all().filter(scanner=scanner).values_list("name", flat=True)
            )

        # make sure this maps to the classes correctly, so use "plannable_activities" instead of with spaces
        scanner_data = {
            "id": scanner.id,
            "name": scanner.name,
            "python_name": scanner.python_name,
            "description": scanner.description,
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


def allowed_to_show(settings: Any, scan_type_name: str):
    # settings is a CaseInsensitiveDict
    setting_name = f"SHOW_{scan_type_name}"
    return False if setting_name not in settings else settings[setting_name]


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
    for scan_type in scantypes:
        # the relevant impacts are not directly coupled to the scanners yet, this might give some small management
        # issues. For now it's fine. A future version can solve this.
        # you need all of them...

        if not allowed_to_show(all_settings, scan_type.name):
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


@lru_cache(maxsize=128, typed=False)
def get_backend_scanmetadata():
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

    published_scan_types = list(ScanType.objects.all().filter(include_in_report=True).values_list("name", flat=True))

    published_url_scan_types = [scan_type for scan_type in published_scan_types if scan_type in url_scan_types]
    published_endpoint_scan_types = [
        scan_type for scan_type in published_scan_types if scan_type in endpoint_scan_types
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
        "published_scan_types": published_scan_types,
        "published_url_scan_types": published_url_scan_types,
        "published_endpoint_scan_types": published_endpoint_scan_types,
    }

    log.error(json.dumps(metadata, indent=2))

    return metadata
