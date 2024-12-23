import copy
from collections import defaultdict
from typing import Any, Dict, List

import simplejson as json
from cachetools import TTLCache, cached
from simplejson import JSONDecodeError

from websecmap.app import log
from websecmap.celery import app
from websecmap.map.logic.map_defaults import get_country, get_organization_type
from websecmap.scanners.models import EndpointGenericScan, Product, ProductHierarchy, ScannerFinding
from websecmap.reporting import time_cache
from websecmap.scanners.scanmanager import Meaning, store_endpoint_scan_result

MAX_RESULTS = 4000


def extract_version_from_nuclei_finding(nuclei_finding: dict) -> str:
    # apparently there can be multiple versions, ive seen some i guess
    version = nuclei_finding.get("evidence", {}).get("extracted-results", [])

    if not version:
        return ""

    # useless version information.
    if version[0] in ["2", "10.0"]:
        return ""

    words_to_remove = ["/", "wordpress", "nginx", "apache", "microsoft-iis", "serv-u", "openssl"]
    for word in words_to_remove:
        # is the 'if' necessary?
        # always be sure that the text to replace matches as it will be lowercase:
        version[0] = version[0].lower()
        if word in version[0]:
            version[0] = version[0].replace(word, "").strip()

    return ", ".join(version)


# caches empty values as well...
# @cached(cache=TTLCache(maxsize=1024, ttl=4 * 60 * 60))
def get_nuclei_product_mapping(use_cache: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    # This is cached as it takes 1 to 3 seconds to load this data.
    if use_cache:
        if my_cached := time_cache.cache_get("login_plaza_product_mapping"):
            return my_cached

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

    if use_cache:
        if mapping:
            time_cache.cache_set("login_plaza_product_mapping", mapping)

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


def get_tech_for_endpoints(endpoint_ids: List[int] = None) -> Dict[int, List[Dict[str, Any]]]:
    # reduces the finding to a product and a vendor
    # this is used to find what dependencies the product has
    # and also to find a cvedetails link.
    # this should also get the tag from the nmap scans. Should be added to the report as info.
    # returns :

    nuclei_product_mapping = get_nuclei_product_mapping()

    # todo: this should be retrieved from an info level item from the report,
    #  not created ad-hoc. -> this should be the method that saves the current state of the art to the report :)
    egpss = (
        EndpointGenericScan.objects.all()
        .filter(
            type__in=["nuclei_technologies", "nuclei_exposed_panels"],
            is_the_latest_scan=True,
            comply_or_explain_is_explained=False,
            # use ordering, otherwise the evidence might look changed while only the order is changed.
            # if a new record is inserted with other evidence etc. This can create a ping pong effect.
        )
        .order_by("type")
    )

    if endpoint_ids:
        egpss = egpss.filter(endpoint__id__in=endpoint_ids)

    egpss = egpss[:MAX_RESULTS]

    # First merge all found records per endpoint: as group_concat etc is missing. This makes it easier with
    # working with various unique products per finding: when they are all in the same list we don't need to
    # inter-check what we did etc.
    # It is normal that you'll get the same findings / mappings over and over...
    findings_per_endpoint = defaultdict(list)
    for epgs in egpss:
        # todo: also add version information from nmap findings
        if nuclei_findings_per_scan := load_json(epgs.evidence):
            findings_per_endpoint[epgs.endpoint.id].extend(nuclei_findings_per_scan)

    # now extract version information of all findings into the findings
    technology_per_endpoint = defaultdict(list)
    for endpoint_id, nuclei_findings in findings_per_endpoint.items():
        # add all possible technologies, uniquely...
        # every endpoint gets their own copy of this data as they will be mogrified with version info
        technology_per_endpoint[endpoint_id] = copy.deepcopy(
            load_products_for_nuclei_findings(nuclei_findings, nuclei_product_mapping)
        )

        # add version information to each of the nodes in the tree:
        for nuclei_finding in nuclei_findings:
            version_info = extract_version_from_nuclei_finding(nuclei_finding)

            if not version_info:
                continue

            products = nuclei_product_mapping[nuclei_finding.get("finding-name", "")]
            for product in products:
                product = product["product"]
                for product_tree in technology_per_endpoint[endpoint_id]:
                    set_value_to_tech_in_tree(
                        product_tree, product_id=product, my_property="version", value=version_info
                    )

    return technology_per_endpoint


@app.task(queue="storage")
def save_get_tech_for_endpoints():
    # get tech for ALL endpoints :)
    tech = get_tech_for_endpoints()

    for endpoint_id, endpoint_tech in tech.items():
        store_endpoint_scan_result(
            scan_type="technology",
            endpoint_id=endpoint_id,
            rating="tech_neutral",
            message="tech_neutral",
            evidence=json.dumps(endpoint_tech),
            meaning={},
        )


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


def set_value_to_tech_in_tree(product_tree: Dict[Any, Any], product_id: int, my_property: str, value: Any):
    if my_property in product_tree and product_tree["product"] == product_id:
        if product_tree[my_property] not in ["unknown", "", value]:
            log.warning(
                "Tyring to set %s to %s, but %s already set to %s. Conflicting findings?",
                value,
                my_property,
                my_property,
                product_tree[my_property],
            )

        product_tree[my_property] = value

    if "related_products" not in product_tree:
        return

    for related_product in product_tree["related_products"]:
        set_value_to_tech_in_tree(related_product, product_id, my_property, value)


def smash_trees(product_trees: List[Dict[Any, Any]]) -> List[Dict[str, Any]]:
    techs = []
    for tree in product_trees:
        techs.extend(smash_tree(tree))

    # now reduce the list to uniques
    # https://stackoverflow.com/questions/11092511/list-of-unique-dictionaries
    return list({v["product"]: v for v in techs}.values())


def smash_tree(product_tree: Dict[Any, Any], technologies: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    # reduces the tree to a list of products
    if not technologies:
        technologies = []

    technologies.append({"product": product_tree["product"], "version": product_tree["version"]})

    if "related_products" in product_tree:
        for related_product in product_tree["related_products"]:
            smash_tree(related_product, technologies)

    return technologies


def prioritize_tech(list_of_techs: List[Dict[str, Any]], product_id) -> List[Dict[str, Any]]:
    my_list_of_techs = copy.deepcopy(list_of_techs)
    # pull product with product id to the front.
    for tech in my_list_of_techs:
        if tech["product"] == product_id:
            my_list_of_techs.remove(tech)
            my_list_of_techs.insert(0, tech)
            break
    return my_list_of_techs


def login_plaza_data(country: str = None, layer: str = None):
    my_country = get_country(country)
    my_layer = get_organization_type(layer)

    scans = (
        EndpointGenericScan.objects.all()
        .filter(
            type="nuclei_exposed_panels",
            is_the_latest_scan=True,
            comply_or_explain_is_explained=False,
            rating__in=["info", "warning", "danger", "low", "medium", "high"],
            endpoint__is_dead=False,
            endpoint__url__is_dead=False,
            endpoint__url__not_resolvable=False,
            endpoint__url__organization__country=my_country,
            endpoint__url__organization__layers=my_layer,
            endpoint__url__organization__is_dead=False,
        )
        .prefetch_related(
            "endpoint", "endpoint__url", "endpoint__url__organization", "endpoint__url__organization__layers"
        )
    )

    # can't use values_list because:
    # "This version of MySQL doesn't yet support 'LIMIT & IN/ALL/ANY/SOME subquery'"
    endpoint_ids = set()
    only_ids = scans
    for only_id in only_ids:
        endpoint_ids.add(only_id.endpoint.id)

    # now we have stuff for endpoint, but we need the correct first item for this panel.
    tech = get_tech_for_endpoints(list(endpoint_ids))

    nuclei_product_mapping = get_nuclei_product_mapping()

    return create_loging_plaza_meanings_for_scans(scans, tech, nuclei_product_mapping)


def create_loging_plaza_meanings_for_scans(scans: List[EndpointGenericScan], tech, nuclei_product_mapping):
    dicts = []

    # don't include the same url over and over again...
    list_of_urls = []

    for scan in scans:
        portals = load_json(scan.evidence)

        if not portals:
            continue

        for portal in portals:
            portal_url = portal.get("evidence", {}).get("matched-at", "")

            if portal_url in list_of_urls:
                continue

            list_of_urls.append(portal_url)

            firstorg = scan.endpoint.url.organization.only("name", "city", "id").first()

            meaning = create_loging_plaza_meanings_for_scans_per_scan(
                portal, scan.endpoint.id, tech, nuclei_product_mapping
            )

            login_plaza_metadata = {
                "organization_name": firstorg.name,
                "organization_city": firstorg.city,
                "organization_id": firstorg.id,
                "url_url": scan.endpoint.url.url,
                "subdomain": scan.endpoint.url.computed_subdomain,
                "domain": f"{scan.endpoint.url.computed_domain}.{scan.endpoint.url.computed_suffix}",
                "last_scan_moment": scan.last_scan_moment,
                "rating_determined_on": scan.rating_determined_on,
                # make it easier to make uniques in the frontend
                "scan_id": scan.id,
            }

            dicts.append({**meaning, **login_plaza_metadata})
    return dicts


def create_loging_plaza_meanings_for_scans_per_scan(portal, endpoint_id, tech, nuclei_product_mapping):
    portal_url = portal.get("evidence", {}).get("matched-at", "")
    extracted = portal.get("evidence", {}).get("extracted-results", "")
    finding_name = portal.get("finding-name", "")

    # make this tech a list (as it used to be), and make sure the prime product is the first one.
    matching_tech = smash_trees(tech.get(endpoint_id, []))
    # prioritized on the this portal finding.
    try:
        if prioritized_product := nuclei_product_mapping.get(finding_name, []):
            prioritized = prioritize_tech(matching_tech, prioritized_product[0]["product"])
        else:
            prioritized = matching_tech
    except KeyError:
        prioritized = matching_tech

    return {
        "portal_name": portal.get("name", "").replace(" - Detect", ""),
        "portal_url": portal_url,
        "portal_extracted": extracted,
        # "endpoint_id": scan.endpoint.id,
        "tech": prioritized,
    }


# there can be multiple portals in the evidence, which is often the case.
def generated_login_portal_meaning_data(portal_scan_evidence: Any, endpoint_id: int) -> Meaning:
    # this is the important stuff that is also used in login plaza, only less... Which in turn has multiple products.
    tech = get_tech_for_endpoints([endpoint_id])
    nuclei_product_mapping = get_nuclei_product_mapping()

    per_portal = []

    for portal in portal_scan_evidence:
        per_portal.append(
            create_loging_plaza_meanings_for_scans_per_scan(portal, endpoint_id, tech, nuclei_product_mapping)
        )

    return per_portal
