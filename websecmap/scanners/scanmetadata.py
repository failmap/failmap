import json
from collections import defaultdict
from typing import Dict, Any, List

from django.db.models import Prefetch

from websecmap.app import log
from websecmap.app.constance import get_all_values
from websecmap.reporting.models import ScanPolicy
from websecmap.scanners.models import Scanner, ScanSubject, ScanType


def dump_scan_config_to_file():
    # This is performed every time this app has started. It will overwrite the shipped scanner settings.
    # This solves a chicken and egg problem of 'what fields are available' before it's possible to access
    # the database.
    # To update the shipped scanner metadata fixture:
    # websecmap dumpdata scanners.scanner scanners.scantype scanners.scantypesecondopinionlink
    # scanners.scantypedocumentationlink scanners.scantypecategory scanners.scanneractivity
    # > websecmap/scanners/fixtures/scanmetadata.json
    data = get_scanners_for_backend()
    try:
        with open("scanmetadata_bootstrap_cache_writable_by_application/constance_definitions.json", "wt") as handle:
            handle.write(json.dumps(data))
    except PermissionError:
        log.error(
            "Permission error: Cannot write scan metadata to "
            "scanmetadata_bootstrap_cache/constance_definitions.json "
            "Make sure this file is writable unless you're not planning to change scanners"
        )
    # Continue operating.
    return


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
            "can_scan_endpoints": True
            if "scan" in planable_activities and scanner.to == ScanSubject.ENDPOINT
            else False,
            "can_discover_endpoints": True
            if "discover" in planable_activities and scanner.to == ScanSubject.ENDPOINT
            else False,
            "can_verify_endpoints": True
            if "verify" in planable_activities and scanner.to == ScanSubject.ENDPOINT
            else False,
            "can_scan_urls": True if "scan" in planable_activities and scanner.to == ScanSubject.URL else False,
            "can_discover_urls": True if "discover" in planable_activities and scanner.to == ScanSubject.URL else False,
            "can_verify_urls": True if "verify" in planable_activities and scanner.to == ScanSubject.URL else False,
            "needs_results_from": [scanner.needs_results_from.id] if scanner.needs_results_from else [],
        }
        results.append(scanner_data)

    return results


def allowed_to_show(settings: Any, scan_type_name: str):
    # settings is a CaseInsensitiveDict
    setting_name = f"SHOW_{scan_type_name}"
    if setting_name not in settings:
        return False

    return settings[setting_name]


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

    for policy in ScanPolicy.objects.all():
        policies[policy.scan_type] += scan_type_policy_to_text(policy)

    # remove redundant items
    new_policies = {}
    for policyx in policies:
        new_policies[policyx] = list(sorted(list(set(policies[policyx]))))

    return dict(new_policies)


def get_scanners_for_frontend():
    # frontend scanners have details about documentation

    all_settings = get_all_values()
    possible_relevant_impacts = get_impacts_per_scan_type()

    results = {}
    scantypes = (
        ScanType.objects.all()
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
