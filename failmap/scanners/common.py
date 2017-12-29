from typing import List

from failmap.organizations.models import Organization


def organizations_from_names(organization_names: List[str]) -> List[Organization]:
    """Turn list of organization names into list of Organization objects.

    Will return all organizations if none are specified.
    """
    # select specified or all organizations to be scanned
    if organization_names:
        organizations = list()
        for organization_name in organization_names:
            try:
                organizations.append(Organization.objects.get(name__iexact=organization_name))
            except Organization.DoesNotExist as e:
                raise Exception("Failed to find organization '%s' by name" % organization_name) from e
    else:
        organizations = Organization.objects.all()

    return organizations
