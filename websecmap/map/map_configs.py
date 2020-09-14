import logging
from typing import List

from websecmap.map.models import Configuration

log = logging.getLogger(__name__)


def filter_map_configs(countries: List = None, organization_types: List = None):
    configs = Configuration.objects.all()
    log.debug("filter for countries: %s" % countries)
    log.debug("filter for organization_types: %s" % organization_types)

    configs = configs.filter(is_reported=True)

    if countries:
        configs = configs.filter(country__in=countries)

    if organization_types:
        configs = configs.filter(organization_type__name__in=organization_types)

    return configs.order_by("display_order").values(
        "country", "organization_type__name", "organization_type", "organization_type__id"
    )


def retrieve(country: str, organization_type_id: int):

    c = Configuration.objects.all().filter(country=country, organization_type=organization_type_id).first()
    if not c:
        raise ValueError(f"Could not find map configuration in {country} with id {organization_type_id}.")

    return c
