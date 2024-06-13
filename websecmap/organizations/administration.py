import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import tldextract

from websecmap.app import log
from websecmap.game.models import OrganizationSubmission
from websecmap.map.models import OrganizationOnLayerOverTime
from websecmap.organizations.models import (
    AlternativeName,
    Coordinate,
    Organization,
    OrganizationType,
    Url,
    OrganizationSurrogateId,
)


def insert_or_update_organization(
    name: str,
    layer: OrganizationType,
    alternative_names: List[str] = None,
    country: str = "NL",
) -> Organization:
    # This can create an organization or update an existing one with new domains. Domains and data are never deleted
    # for now. If that would be the case: older domains might not be monitored while the government is still responsible
    # for them. This is a hard problem. We could just make this list authoritative which is much easier.

    if alternative_names is None:
        alternative_names = []

    # some sources have spaces in their names
    name = name.strip()
    alternative_names = [x.strip() for x in alternative_names]

    organization = find_organization_by_names_and_layer_and_country([name] + alternative_names, layer, country)

    # add new websites if this already exists.
    if not organization:
        log.debug("Creating new organization: %s", name)
        organization = Organization.objects.create(name=name, created_on=datetime.now(timezone.utc), country=country)
        organization.layers.add(layer)

    return organization


def insert_or_update_geojson_on_organization(
    organization: Organization, geojson_data: Union[List[Any], Dict[Any, Any]], geojson_type: str = "Point"
) -> Coordinate:
    coordinate = Coordinate.objects.all().filter(organization=organization, is_dead=False).first()

    # data is the same, updating is useless...
    if coordinate and coordinate.area == geojson_data:
        return coordinate

    if coordinate:
        coordinate.is_dead = True
        coordinate.save()

    coordinate = Coordinate.objects.create(
        organization=organization,
        is_dead=False,
        geojsontype=geojson_type,
        area=geojson_data,
    )

    return coordinate


def find_organization_by_names_and_layer_and_country(
    names: List[str], layer: OrganizationType = None, country: str = "NL", excluding: List[Organization] = None
) -> Optional[Organization]:
    if excluding is None:
        excluding = []

    for name in names:
        org_query = Organization.objects.all().filter(is_dead=False)

        if excluding:
            org_query = org_query.exclude(id__in=[x.id for x in excluding])

        if country:
            org_query = org_query.filter(country=country)

        if layer:
            org_query = org_query.filter(layers=layer)

        # try normal name:
        normal_name_query = org_query
        normal_name_query = normal_name_query.filter(name__iexact=name)
        if organization := normal_name_query.first():
            return organization

        # try alternative name:
        alternative_name_query = org_query
        alternative_name_query = alternative_name_query.filter(alternative_names__name__iexact=name)
        if organization := alternative_name_query.first():
            return organization

    return None


def add_urls_to_organization(organization: Organization, urls: List[str], origin: str = ""):
    log.debug("Adding sites to organization: %s, %s", organization, urls)
    for url in urls:
        organization.add_url(url, origin=origin)


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


def merge_similar_organizations():
    # Merges organizations that have the same name over different layers. Makes sure that the oldest organization
    # stays and the newest one is just dissolved. Make sure that the urls from the new organizations are also
    # moved if they are missing in the old one.  # except when it's rijksoverheid.nl

    handled_organizations = []
    for organization in Organization.objects.all().filter(is_dead=False).order_by("id"):
        handled_organizations.append(organization)
        log.debug("Merging organization %s, id: %s", organization, organization.id)
        for name in organization.names:
            # we don't care about the layer, it might be any layer: that is the point of merging
            while existing_organization := find_organization_by_names_and_layer_and_country(
                names=[name], country=organization.country, excluding=handled_organizations
            ):
                # make sure it never re-surfaces, even if the organization is skipped / not merged.
                handled_organizations.append(existing_organization)

                if existing_organization.created_on < organization.created_on:
                    log.debug("- SKIPPING, existing organization is older and should thus not be merged (weird)")
                    continue

                log.debug("- Found duplicate organization: %s, %s", existing_organization, existing_organization.id)
                merge_organizations(existing_organization, organization)


def force_merge_organizations(organizations: List[Organization], also_delete=False):
    # Merge organizations from the admin interface, those who have different names (or slightly similar) into one.
    # You are able to select a dozen organizations at a time and they will all be merged into the oldest one.
    # Now you can search for "mijnen" to find:
    # - Staatstoezicht op de Mijnen (SODM)
    # - Staatstoezicht op de Mijnen (SodM)
    # - Staatstoezicht op de Mijnen
    # - etc...

    sorted_organizations = sorted(organizations, key=lambda o: o.created_on)
    oldest_organization = sorted_organizations[0]
    other_organizations = sorted_organizations[1:]

    for other_organization in other_organizations:
        log.debug("Merging organization %s into %s.", other_organization.id, oldest_organization.id)
        merge_organizations(org_from=other_organization, org_to=oldest_organization)
        if also_delete:
            other_organization.delete()


def merge_organizations(org_from: Organization, org_to: Organization):
    # move urls
    for url in Url.objects.all().filter(organization=org_from):
        log.debug("- - Transferring url %s", url)
        url.organization.add(org_to)

    # move alternative names
    for alt_name in org_from.alternative_names.all():
        log.debug("- - Transferring alt name %s", alt_name)
        org_to.alternative_names.add(alt_name)

    if org_from.name != org_to.name:
        log.debug("- - Names differ, setting name from source to alt name in target")
        org_to.alternative_names.add(AlternativeName.objects.create(name=org_from.name))

    # move layers
    for layer in org_from.layers.all():
        log.debug("- - Transferring layer %s", layer)
        org_to.layers.add(layer)

    # also move the organization type to layer if that didn't happen yet:
    # if org_from.type:
    #     org_to.layers.add(org_from.type)

    # move surrogate ID's
    OrganizationSurrogateId.objects.all().filter(organization=org_from).update(organization=org_to)

    # we don't merge the coordinates, as they should be correct in import.
    # even if the constraint is cascade, this will just restrict sometimes. Nice bugs :)
    # assume the newest coordinates are the best coordinates.
    Coordinate.objects.all().filter(organization=org_from).update(organization=org_to)

    # the old organization does not exist anymore, so it cannot be tracked over time
    # and its not really feasible to merge it with the existing one that is already tracked...
    OrganizationOnLayerOverTime.objects.all().filter(organization=org_from).delete()

    # just kill them all and then revive the latest
    coordinates = Coordinate.objects.all().filter(organization=org_to)
    for coordinate in coordinates:
        coordinate.kill()

    if newest_coordinates := Coordinate.objects.all().filter(organization=org_to).last():
        newest_coordinates.revive()

    # Also move all game submissions, which is a bit easier...
    OrganizationSubmission.objects.all().filter(organization_in_system=org_from).update(organization_in_system=org_to)

    # move fields if not empty:
    fields = ["internal_notes", "twitter_handle", "wikidata", "wikipedia", "surrogate_id", "written_address"]
    for field in fields:
        value = getattr(org_from, field)
        if value and not getattr(org_to, field):
            log.debug("- - Moving field data from field %s with value %s", field, value)
            setattr(org_to, field, value)

    org_to.save()

    # delete existing organization as it is a duplicate
    org_from.is_dead = True
    org_from.is_dead_reason = "Was a duplicate of an older organization."
    org_from.is_dead_since = datetime.now(timezone.utc)
    org_from.save()
