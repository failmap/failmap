from websecmap.reporting.models import ScanPolicy
from websecmap.scanners.models import Scanner, ScanSubject, ScanType


def dump_scan_config_to_file():
    # This is performed every time this app has started. It will overwrite the shipped scanner settings.
    # This solves a chicken and egg problem of 'what fields are available' before it's possible to access
    # the database.
    ...


# this will be moved to __init__.py
def read_scan_config_from_file():
    ...


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

        scanner_data = {
            "id": scanner.id,
            "name": scanner.name,
            "description": scanner.description,
            "plannable_activities": sorted(planable_activities),
            "creates endpoint scan types": sorted(endpoint_scan_types),
            "creates url scan types": sorted(url_scan_types),
            "can scan endpoints": True
            if "scan" in planable_activities and scanner.to == ScanSubject.ENDPOINT
            else False,
            "can discover endpoints": True
            if "discover" in planable_activities and scanner.to == ScanSubject.ENDPOINT
            else False,
            "can verify endpoints": True
            if "verify" in planable_activities and scanner.to == ScanSubject.ENDPOINT
            else False,
            "can scan urls": True if "scan" in planable_activities and scanner.to == ScanSubject.URL else False,
            "can discover urls": True if "discover" in planable_activities and scanner.to == ScanSubject.URL else False,
            "can verify urls": True if "verify" in planable_activities and scanner.to == ScanSubject.URL else False,
            "needs results from": [scanner.needs_results_from.id] if scanner.needs_results_from else [],
        }
        results.append(scanner_data)

    return results


def get_scanners_for_frontend():
    # frontend scanners have details about documentation and stuff...
    # this is issue focussed, example:
    # dnssec: {
    #         name: "dnssec",
    #         "second opinion links": [sol.zonemaster],
    #         "documentation links": [dol.wikipedia_dnssec],
    #         "relevant impacts": ["high"],
    #         statistics: {
    #           good: [
    #             {
    #               label: 'DNSSEC correct', explanation: 'DNSSEC seems to be implemented sufficiently.'
    #             }],
    #           medium: [],
    #           bad: [{
    #             label: 'DNSSEC incorrect',
    #             explanation: 'DNSSEC is incorrectly or not configured (errors found).'
    #           }]
    #         },
    #         category: ['dns', 'confidentiality', 'integrity']
    #       },

    # todo: get constance settings for what is shown in the frontend.

    results = []
    for scan_type in ScanType.objects.all():
        # the relevant impacts are not directly coupled to the scanners yet, this might give some small management
        # issues. For now it's fine. A future version can solve this.
        # you need all of them...
        possible_relevant_impacts = (
            ScanPolicy.objects.all()
            .filter(scan_type=scan_type.name)
            .values_list("high", "medium", "low", "ok", named=True)
        )
        all_impacts = []
        for rel in possible_relevant_impacts:
            if rel.high:
                all_impacts.append("high")
            if rel.medium:
                all_impacts.append("medium")
            if rel.low:
                all_impacts.append("low")
            if rel.ok:
                all_impacts.append("ok")

        data = {
            "name": scan_type.name,
            "id": scan_type.id,
            "category": sorted(list(scan_type.category.all().values_list("name", flat=True))),
            "relevant impacts": sorted(list(set(all_impacts))),
            "documentation links": list(scan_type.documentation_links.all().values("url", "friendly_name")),
            "second opinion links": list(scan_type.second_opinion_links.all().values("url", "friendly_name")),
        }

        results.append(data)

    return results


SCANNERS = get_scanners_for_backend()
AVAILABLE_SCANNERS = []
ENDPOINT_SCAN_TYPES = []
URL_SCAN_TYPES = []
for scanner in SCANNERS:
    AVAILABLE_SCANNERS += scanner["name"]
    ENDPOINT_SCAN_TYPES = list(set(ENDPOINT_SCAN_TYPES + scanner["creates endpoint scan types"]))
    URL_SCAN_TYPES = list(set(URL_SCAN_TYPES + scanner["creates url scan types"]))

ALL_SCAN_TYPES = URL_SCAN_TYPES + ENDPOINT_SCAN_TYPES

# convert endpoint scan types to scanners, so we know what endpoint scan type belongs to what scanner
SCAN_TYPES_TO_SCANNER = {}
for scanner in SCANNERS:
    for scan_type in scanner["creates endpoint scan types"]:
        SCAN_TYPES_TO_SCANNER[scan_type] = scanner

    for scan_type in scanner["creates url scan types"]:
        SCAN_TYPES_TO_SCANNER[scan_type] = scanner

SCANNERS_BY_NAME = {}
for scanner in SCANNERS:
    SCANNERS_BY_NAME[scanner["name"]] = scanner
