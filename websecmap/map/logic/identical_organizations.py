import logging
from typing import List

from websecmap.organizations.models import Organization, Url

log = logging.getLogger(__package__)

"""
Todo: also figure out organizations with duplicate names.
"""


def triage_identical():
    """
    This is mainly to clean up the Dutch Government Almanak, which has tons of duplicate data. For each
    tax office they use the same domains. Ministry of defense has tons of the same domains under different names.

    :return:
    """
    organizations = Organization.objects.all().filter(country="NL", type__name="government")
    urls = {}
    for organization in organizations:
        urls[organization.pk] = set(
            Url.objects.all()
            .filter(organization=organization, is_dead=False, not_resolvable=False, computed_subdomain="")
            .exclude(url="rijksoverheid.nl")
        )
    # gather all duplicates
    for organization in organizations:
        # Some organizations are placeholders.
        if not urls[organization.pk]:
            continue
        duplicate_organization_ids = []
        duplicate_organizations = []
        for possible_duplicate in organizations:
            # Don't see yourself as a duplicate
            if possible_duplicate.pk == organization.pk:
                continue
            if urls[organization.pk] == urls[possible_duplicate.pk]:
                duplicate_organization_ids.append(possible_duplicate.id)
                duplicate_organizations.append(possible_duplicate)
        if duplicate_organizations:
            print(f"Identical organizations to {organization.id}: {organization.name}")
            print(f"With urls: {urls[organization.pk]}")
            for duplicate_organization in duplicate_organizations:
                print(f" - Identical to organizations {duplicate_organization.id}: {duplicate_organization.name}")
            print(f"All duplicate ids: {duplicate_organization_ids}")


def delete_organizations(ids: List):
    deleted = Organization.objects.all().filter(id__in=ids).delete()
    print(f"Deleted: {deleted}.")
