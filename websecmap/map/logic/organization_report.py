import logging

from django.utils.text import slugify

from websecmap.map.logic.map_defaults import (
    DEFAULT_COUNTRY,
    DEFAULT_LAYER,
    get_country,
    get_organization_type,
    get_when,
)
from websecmap.organizations.models import Organization
from websecmap.reporting.diskreport import retrieve_report

log = logging.getLogger(__package__)


def get_organization_report_by_name(
    country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER, organization_name=None, weeks_back=0
):

    organization = Organization.objects.filter(
        computed_name_slug=slugify(organization_name),
        country=get_country(country),
        type=get_organization_type(organization_type),
        is_dead=False,
    ).first()

    log.debug("- %s %s %s ", organization_name, get_country(country), get_organization_type(organization_type))
    log.debug(organization)

    if not organization:
        return {}

    return get_organization_report_by_id(organization.pk, weeks_back)


def get_organization_report_by_id(organization_id: int, weeks_back: int = 0):
    # todo: check if the organization / layer is displayed on the map.

    when = get_when(weeks_back)

    organization = Organization.objects.all().filter(pk=organization_id)
    if not organization:
        return {}

    ratings = organization.filter(organizationreport__at_when__lte=when)
    try:
        values = ratings.values(
            "organizationreport__at_when",
            "name",
            "pk",
            "twitter_handle",
            "organizationreport__id",
            "organizationreport__high",
            "organizationreport__medium",
            "organizationreport__low",
            "organizationreport__ok",
        ).latest("organizationreport__at_when")
    except Organization.DoesNotExist:
        return {}

    report_data = retrieve_report(values["organizationreport__id"], "OrganizationReport")

    report = {
        "name": values["name"],
        "slug": slugify(values["name"]),
        "id": values["pk"],
        "twitter_handle": values["twitter_handle"],
        "when": values["organizationreport__at_when"].isoformat(),
        # fixing json being presented and escaped as a string, this makes it a lot slowr
        # had to do this cause we use jsonfield, not django_jsonfield, due to rendering map widgets in admin
        "calculation": report_data,
        "promise": "",
        "high": values["organizationreport__high"],
        "medium": values["organizationreport__medium"],
        "low": values["organizationreport__low"],
        "ok": values["organizationreport__ok"],
    }

    return report
