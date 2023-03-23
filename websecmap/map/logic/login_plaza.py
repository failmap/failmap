from collections import defaultdict
from typing import Dict, Any, List

import simplejson as json
from django.forms import model_to_dict
from simplejson import JSONDecodeError

from websecmap.app import log
from websecmap.map.logic.map_defaults import get_country, get_organization_type
from websecmap.scanners.models import EndpointGenericScan, ScannerFinding, Product, ProductHierarchy

MAX_RESULTS = 4000


def extract_version_from_nuclei_finding(nuclei_finding: dict) -> str:
    # apparently there can be multiple versions, ive seen some i guess
    version = nuclei_finding.get("evidence", {}).get("extracted-results", [])

    if not version:
        return ""

    # use the version logic from nmap scanner here...
    # replace cms / ['WordPress 6.1.1'] to wordpress / [6.1.1]
    if "wordpress" in version[0].lower():
        version[0] = version[0].replace("wordpress", "").strip()

    if "nginx" in version[0].lower():
        version[0] = version[0].replace("nginx/", "").strip()

    return ", ".join(version)


def get_nuclei_product_mapping() -> Dict[str, List[Dict[str, Any]]]:
    # maps scanner findings to all products related to them.
    # the finding name lists to a number of products and related products.
    # todo: add time cache

    # product_prefetch = Prefetch("product",
    # queryset=Product.objects.filter(is_irrelevant=False), to_attr="product_set")
    scannerfindings = ScannerFinding.objects.all()  # .prefetch_related(product_prefetch)

    mapping = defaultdict(list)
    for scannerfinding in scannerfindings:
        for product in scannerfinding.product_set.all():
            mapping[scannerfinding.name].append({"product": product.id, "version": "unknown"})

            # todo: move this to a nested set tree or something that reduces this to one query.
            # just assume two layers of nesting now. Probably a nested set tree or so.
            # Is this just as much as a human would understand anyway?
            # todo: add relation finding to product class, not here.
            related_products = get_nested_products_in_an_inefficient_way(product)
            for related_product in related_products:
                mapping[scannerfinding.name].append({"product": related_product.id, "version": "unknown"})
                related_related_products = get_nested_products_in_an_inefficient_way(related_product)
                for related_related_product in related_related_products:
                    mapping[scannerfinding.name].append({"product": related_related_product.id, "version": "unknown"})

    return mapping


def get_products():
    # This is loaded into the web app, this saves a lot of redundant data.
    # the client from here on only gets product-ids / tech-ids.
    return {str(product.id): product_to_dict(product) for product in Product.objects.filter(is_irrelevant=False)}


def product_to_dict(product: Product) -> Dict[str, Any]:
    return {
        "id": product.id,
        "name": product.name,
        "slug": product.slug,
        "vendor": model_to_dict(product.vendor) if product.vendor else {},
        "cve_details_link": product.cve_details_link,
        "open_cve_link": product.open_cve_link,
        "is_open_source": product.is_open_source,
        "common_execution_context": product.common_execution_environment,
        "goal": product.goal.name if product.goal else "",
        "tags": list(product.tags.all().values_list("name", flat=True)),
        "intended_use_case_description": product.intended_use_case_description,
    }


def get_nested_products_in_an_inefficient_way(product_id: Product) -> List[Product]:
    return list(
        Product.objects.filter(
            id__in=ProductHierarchy.objects.all()
            .filter(product=product_id, product__is_irrelevant=False)
            .values_list("related_product", flat=True)
        )
    )


def get_tech(endpoint_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    # reduces the finding to a product and a vendor
    # this is used to find what dependencies the product has
    # and also to find a cvedetails link.
    # this should also get the tag from the nmap scans. Should be added to the report as info.
    # returns :

    nuclei_product_mapping = get_nuclei_product_mapping()

    # todo: this should be retrieved from an info level item from the report,
    #  not created ad-hoc.
    egpss = EndpointGenericScan.objects.all().filter(
        endpoint__id__in=endpoint_ids,
        type__in=["nuclei_technologies", "nuclei_exposed_panels"],
        is_the_latest_scan=True,
        comply_or_explain_is_explained=False,
    )[:MAX_RESULTS]

    technology_per_endpoint = defaultdict(list)

    for epgs in egpss:
        # do not add things twice to the list of technologies:
        already_found_technology = []
        already_found_technology_with_version_info = []
        try:
            nuclei_findings = json.loads(epgs.evidence)
        except JSONDecodeError:
            continue

        # nuclei finding =
        # {"template-id": "wordpress-detect", "name": "WordPress Detect", "finding-name":
        # "nuclei_wordpress_detect", "evidence": {"extracted-results": ["5.8.3"], "matched-at""}},
        for nuclei_finding in nuclei_findings:
            version_info = extract_version_from_nuclei_finding(nuclei_finding)
            technologies = nuclei_product_mapping[nuclei_finding.get("finding-name", "")]

            log.debug(f"Found {len(technologies)} technologies for {nuclei_finding.get('finding-name', '')}.")

            # first tech is always the top of the tree. So add the version there:
            if version_info and technologies:
                technologies[0]["version"] = version_info

            # each finding can contain multiple products, there might be duplicates per endpoint ofc
            # especially with things like joomla and other client technologies.
            for technology in technologies:
                if technology["product"] in already_found_technology:
                    # replace the current one if this one has a version and the other one doesnt:
                    # so if this doesn't have a version, then go on.
                    # Also if we already have a version, just continue
                    if not version_info or technology["product"] in already_found_technology_with_version_info:
                        continue

                    # now we have added this tech in the past, but without version info. Add it.
                    for tech_missing_version in technology_per_endpoint[epgs.endpoint.id]:
                        if tech_missing_version["product"] == technology["product"]:
                            tech_missing_version["version"] = version_info
                            break

                # optimize to include a version number if it is available.
                if version_info:
                    already_found_technology_with_version_info.append(technology["product"])
                already_found_technology.append(technology["product"])
                technology_per_endpoint[epgs.endpoint.id].append(technology)

    return technology_per_endpoint


def login_plaza_data(country: str = None, layer: str = None):
    my_country = get_country(country)
    my_layer = get_organization_type(layer)

    scans = EndpointGenericScan.objects.all().filter(
        type="nuclei_exposed_panels",
        is_the_latest_scan=True,
        comply_or_explain_is_explained=False,
        rating__in=["info", "warning", "danger"],
        endpoint__is_dead=False,
        endpoint__url__is_dead=False,
        endpoint__url__not_resolvable=False,
        endpoint__url__organization__country=my_country,
        endpoint__url__organization__layers=my_layer,
    )

    # can't use values_list because:
    # "This version of MySQL doesn't yet support 'LIMIT & IN/ALL/ANY/SOME subquery'"
    endpoint_ids = set()
    only_ids = scans
    for only_id in only_ids:
        endpoint_ids.add(only_id.endpoint.id)

    tech = get_tech(list(endpoint_ids))

    dicts = []
    # don't include the same url over and over again...
    list_of_urls = []

    for scan in scans:
        log.debug(scan)

        try:
            portals = json.loads(scan.evidence)
        except JSONDecodeError:
            portals = []

        if not portals:
            continue

        for portal in portals:
            portal_url = portal.get("evidence", {}).get("matched-at", "")

            if portal_url in list_of_urls:
                continue

            list_of_urls.append(portal_url)

            dicts.append(
                {
                    "organization_name": scan.endpoint.url.organization.first().name,
                    "organization_id": scan.endpoint.url.organization.first().id,
                    "url_url": scan.endpoint.url.url,
                    "subdomain": scan.endpoint.url.computed_subdomain,
                    "domain": f"{scan.endpoint.url.computed_domain}.{scan.endpoint.url.computed_suffix}",
                    "last_scan_moment": scan.last_scan_moment,
                    "rating_determined_on": scan.rating_determined_on,
                    "portal_name": portal.get("name", "").replace(" - Detect", ""),
                    "portal_url": portal_url,
                    "portal_extracted": portal.get("evidence", {}).get("extracted-results", ""),
                    # make it easier to make uniques in the frontend
                    "scan_id": scan.id,
                    # "endpoint_id": scan.endpoint.id,
                    "tech": tech.get(scan.endpoint.id, []),
                }
            )
    return dicts
