from websecmap.map.logic.map_defaults import get_country, get_organization_type
from websecmap.map.models import Configuration
from websecmap.scanners.models import EndpointGenericScan

MAX_RESULTS = 50000


def cookie_plaza_data(country: str = None, layer: str = None):
    scans = (
        EndpointGenericScan.objects.all()
        .filter(
            type="web_privacy_cookie_products_no_consent",
            is_the_latest_scan=True,
            comply_or_explain_is_explained=False,
            rating__in=["medium"],
            endpoint__is_dead=False,
            endpoint__url__is_dead=False,
            endpoint__url__not_resolvable=False,
            endpoint__url__organization__is_dead=False,
        )
        .prefetch_related(
            "endpoint", "endpoint__url", "endpoint__url__organization", "endpoint__url__organization__layers"
        )
        .order_by("-rating_determined_on")
    )
    if country:
        scans = scans.filter(endpoint__url__organization__country=get_country(country))
    if layer:
        # this checks if the layer is visible
        scans = scans.filter(endpoint__url__organization__layers=get_organization_type(layer))
    else:
        # only layers that are visible
        scans = scans.filter(
            endpoint__url__organization__layers__in=list(
                Configuration.objects.all().filter(is_displayed=True).values_list("organization_type", flat=True)
            )
        )

    scans = scans[:MAX_RESULTS]

    records = []
    stats = {}

    # layers upon layers upon layers :)
    for scan in scans:
        for organization in scan.endpoint.url.organization.all():
            for layer in organization.layers.all():
                if layer.name not in stats:
                    stats[layer.name] = {
                        "organizations_with_tracking_cookies": set(),
                        "urls_with_tracking_cookies": set(),
                        "organization_details": {},
                    }
                if organization.id not in stats[layer.name]["organizations_with_tracking_cookies"]:
                    stats[layer.name]["organization_details"][str(organization.id)] = {
                        "id": organization.id,
                        "name": organization.name,
                        "city": organization.city,
                        "urls_with_tracking_cookies": [],
                    }

                stats[layer.name]["organizations_with_tracking_cookies"].add(organization.id)
                stats[layer.name]["urls_with_tracking_cookies"].add(scan.endpoint.url.url)
                stats[layer.name]["organization_details"][str(organization.id)]["urls_with_tracking_cookies"].append(
                    scan.endpoint.url.url
                )

                records.append(
                    {
                        "organization_name": organization.name,
                        "organization_id": organization.id,
                        "organization_city": organization.city,
                        "country": organization.country.code,
                        "layer": layer.name,
                        "url_url": scan.endpoint.url.url,
                        "subdomain": scan.endpoint.url.computed_subdomain,
                        "domain": f"{scan.endpoint.url.computed_domain}.{scan.endpoint.url.computed_suffix}",
                        "last_scan_moment": scan.last_scan_moment.isoformat(),
                        "rating_determined_on": scan.rating_determined_on.isoformat(),
                        "cookies": scan.meaning,
                        # make it easier to make uniques in the frontend
                        "scan_id": scan.id,
                    }
                )

    # stats cannot be sets as those cannot be serialized
    for stat in stats:
        # sets dont have ordering?
        stats[stat]["organizations_with_tracking_cookies"] = list(
            sorted(stats[stat]["organizations_with_tracking_cookies"])
        )
        stats[stat]["urls_with_tracking_cookies"] = list(sorted(stats[stat]["urls_with_tracking_cookies"]))

    return records, stats
