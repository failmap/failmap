import simplejson as json
from simplejson import JSONDecodeError

from websecmap.app import log
from websecmap.map.logic.map_defaults import get_country, get_organization_type
from websecmap.scanners.models import EndpointGenericScan


def login_plaza_data(country: str = None, layer: str = None):
    my_country = get_country(country)
    my_layer = get_organization_type(layer)

    # limit to 500 results to speed up response time
    scans = EndpointGenericScan.objects.all().filter(
        type__in=["nuclei_exposed_panels"],
        is_the_latest_scan=True,
        comply_or_explain_is_explained=False,
        rating__in=["info", "warning", "danger"],
        endpoint__is_dead=False,
        endpoint__url__is_dead=False,
        endpoint__url__not_resolvable=False,
        endpoint__url__organization__country=my_country,
        endpoint__url__organization__type=my_layer,
    )[:500]

    dicts = []

    for scan in scans:
        log.debug(scan)

        try:
            portals = json.loads(scan.evidence)
        except JSONDecodeError:
            portals = []

        if not portals:
            continue

        dicts.extend(
            {
                "organization_name": scan.endpoint.url.organization.first().name,
                "organization_id": scan.endpoint.url.organization.first().id,
                "url_url": scan.endpoint.url.url,
                "subdomain": scan.endpoint.url.computed_subdomain,
                "domain": f"{scan.endpoint.url.computed_domain}.{scan.endpoint.url.computed_suffix}",
                "last_scan_moment": scan.last_scan_moment,
                "rating_determined_on": scan.rating_determined_on,
                "portal_name": portal.get("name", "").replace(" - Detect", ""),
                "portal_url": portal.get("evidence", {}).get("matched-at", ""),
                "portal_extracted": portal.get("evidence", {}).get("extracted-results", ""),
            }
            for portal in portals
        )
    return dicts
