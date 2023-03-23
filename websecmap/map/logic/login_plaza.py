from collections import defaultdict
from cachetools import cached, TTLCache
from typing import Dict, Any, List

import simplejson as json
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


# caches empty values as well...
# @cached(cache=TTLCache(maxsize=1024, ttl=4 * 60 * 60))
def get_nuclei_product_mapping() -> Dict[str, List[Dict[str, Any]]]:
    # maps scanner findings to all products related to them.
    # the finding name lists to a number of products and related products.

    # product_prefetch = Prefetch("product",
    # queryset=Product.objects.filter(is_irrelevant=False), to_attr="product_set")
    scannerfindings = ScannerFinding.objects.all()  # .prefetch_related(product_prefetch)

    mapping = defaultdict(list)
    for scannerfinding in scannerfindings:
        for product in scannerfinding.product_set.all():
            mapping[scannerfinding.name].append(
                {
                    "product": product.id,
                    "version": "unknown",
                    "related_products": get_nested_products_in_an_inefficient_way(product.id),
                }
            )

    return mapping


def get_products():
    # This is loaded into the web app, this saves a lot of redundant data.
    # the client from here on only gets product-ids / tech-ids.
    return {str(product.id): product.as_dict() for product in Product.objects.filter(is_irrelevant=False)}


@cached(cache=TTLCache(maxsize=1024, ttl=4 * 60 * 60))
def get_nested_products_in_an_inefficient_way(product_id: int, max_depth: int = 3) -> list[dict[str, Any]]:

    # prevent infinite circular references
    max_depth -= 1
    if max_depth < 1:
        return []

    if max_depth > 10:
        raise ValueError(
            "We've set a recursion limit because of inefficient programming of hierarchical data "
            "retrieval. Either you have a recursion in your product relations or you actually have"
            " a depth > 10. If the last one is true, we salute you."
        )

    # todo: move this to a nested set tree or something that reduces this to one query.
    related = ProductHierarchy.objects.filter(product=product_id, product__is_irrelevant=False).order_by("relationship")
    return [
        {
            "product": related.related_product.pk,
            "version": "unknown",
            "relationship": related.relationship.slug,
            "related_products": get_nested_products_in_an_inefficient_way(related.related_product, max_depth),
        }
        for related in related
    ]


def get_tech_for_endpoints(endpoint_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
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

    # It is normal that you'll get the same findings / mappings over and over.
    technology_per_endpoint = defaultdict(list)

    for epgs in egpss:
        # [{"template-id": "wordpress-detect", "name": "WordPress D", "finding-name":
        # "nuclei_wordpress_detect", "evidence": {"extracted-results": ["5.8.3"], "matched-at""}}]
        nuclei_findings = load_json(epgs.evidence)

        # add all possible technologies, uniquely
        technology_per_endpoint[epgs.endpoint.id] = load_products_for_nuclei_findings(
            nuclei_findings, nuclei_product_mapping
        )

        # add version information to each of the nodes in the tree:
        for nuclei_finding in nuclei_findings:
            version_info = extract_version_from_nuclei_finding(nuclei_finding)

            if not version_info:
                continue

            products = nuclei_product_mapping[nuclei_finding.get("finding-name", "")]
            for product in products:
                product = product["product"]
                for product_tree in technology_per_endpoint[epgs.endpoint.id]:
                    set_value_to_tech_in_tree(product_tree, product_id=product, property="version", value=version_info)

    return technology_per_endpoint


def load_products_for_nuclei_findings(
    nuclei_findings: List[Dict[str, Any]], nuclei_product_mapping
) -> List[Dict[str, Any]]:
    prods = []

    # do not add "drupal" three times if there are various findings for this
    found_product_ids = set()

    for nuclei_finding in nuclei_findings:
        # apache-ubuntu page = two technologies: apache + ubuntu linux
        # These will usually not really overlap, complex tree mutations is for another day
        products = nuclei_product_mapping[nuclei_finding.get("finding-name", "")]
        for product in products:
            product_id = product["product"]
            if product_id in found_product_ids:
                continue
            found_product_ids.add(product_id)
            prods.append(product)

    return prods


def load_json(data: str):
    try:
        return json.loads(data)
    except JSONDecodeError:
        return []


def set_value_to_tech_in_tree(product_tree: Dict[Any, Any], product_id: int, property: str, value: Any):

    if property in product_tree and product_tree["product"] == product_id:
        product_tree[property] = value

    if "related_products" not in product_tree:
        return

    for related_product in product_tree["related_products"]:
        set_value_to_tech_in_tree(related_product, product_id, property, value)


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

    tech = get_tech_for_endpoints(list(endpoint_ids))

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
