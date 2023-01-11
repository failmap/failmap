import re
from typing import List, Any, Dict, Optional, Union, Tuple

from django.utils import timezone

from websecmap.app import log
from websecmap.organizations.models import Organization, OrganizationType, Coordinate
import tldextract


def insert_or_update_organization(
    name: str,
    layer: OrganizationType,
    geojson_data: Union[List[Any], Dict[Any, Any]],
    geojson_type: str = "Point",
    alternative_names: List[str] = None,
) -> Organization:
    # This can create an organization or update an existing one with new domains. Domains and data are never deleted
    # for now. If that would be the case: older domains might not be monitored while the government is still responsible
    # for them. This is a hard problem. We could just make this list authoritative which is much easier.

    if alternative_names is None:
        alternative_names = []

    organization = find_organization_by_names_and_layer([name] + alternative_names, layer)

    # add new websites if this already exists.
    if not organization:
        log.debug("Creating new organization: %s", name)
        organization = Organization.objects.create(name=name, type=layer, created_on=timezone.now())

    coordinate = Coordinate.objects.all().filter(organization=organization, is_dead=False).first()

    # data is the same, updating is useless...
    if coordinate and coordinate.area == geojson_data:
        return organization

    if coordinate:
        coordinate.is_dead = True
        coordinate.save()

    Coordinate.objects.create(
        organization=organization,
        is_dead=False,
        geojsontype=geojson_type,
        area=geojson_data,
    )

    return organization


def find_organization_by_names_and_layer(names: List[str], layer: OrganizationType) -> Optional[Organization]:
    for name in names:
        if organization := Organization.objects.all().filter(name__iexact=name, type=layer).first():
            return organization
    return None


def add_urls_to_organization(organization: Organization, urls: List[str]):
    log.debug("Adding sites to organization: %s, %s", organization, urls)
    for url in urls:
        organization.add_url(url)


def get_or_create_layer(name: str) -> OrganizationType:
    layer, _ = OrganizationType.objects.all().get_or_create(name=name)
    return layer


def retrieve_possible_urls_from_unfiltered_input(unfiltered_input: str) -> Tuple[List[str], int]:
    # Protocols are irrelevant:
    # There might be data sticking in front of the protocol, thus use an extra space.
    unfiltered_input = unfiltered_input.replace("http://", " ")
    unfiltered_input = unfiltered_input.replace("https://", " ")

    # Allow CSV, newlines, tabs and space-split input
    unfiltered_input = unfiltered_input.replace(",", " ")
    unfiltered_input = unfiltered_input.replace("\n", " ")
    unfiltered_input = unfiltered_input.replace("\t", " ")

    # split email addresses from their domain
    unfiltered_input = unfiltered_input.replace("@", " ")

    # Split also removes double spaces etc
    unfiltered_input_list: List[str] = unfiltered_input.split(" ")

    # now remove _all_ whitespace characters
    unfiltered_input_list = [re.sub(r"\s+", " ", u) for u in unfiltered_input_list]

    # remove port numbers and paths
    unfiltered_input_list = [re.sub(r":[^\s]*", "", u) for u in unfiltered_input_list]

    # remove paths, directories etc
    unfiltered_input_list = [re.sub(r"/[^\s]*", "", u) for u in unfiltered_input_list]

    # Remove empty values
    while "" in unfiltered_input_list:
        unfiltered_input_list.remove("")

    # make list unique
    total_non_unique_items = len(unfiltered_input_list)
    unfiltered_input_list = list(set(unfiltered_input_list))
    total_unique_items = len(unfiltered_input_list)
    duplicates_removed = total_non_unique_items - total_unique_items

    # domains can still be wrong, such as "info" (or other tld like museum).
    # Check for all domains that it has a valid tld:
    has_tld = [
        domain
        for domain in unfiltered_input_list
        if tldextract.extract(domain).suffix and tldextract.extract(domain).domain
    ]

    # make sure the list is in alphabetical order, which is nice for testability.
    return sorted(has_tld), duplicates_removed
