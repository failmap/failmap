import logging

import simplejson as json
from django.utils import timezone
from django.utils.text import slugify

from websecmap.map.logic.map_defaults import (DEFAULT_COUNTRY, DEFAULT_LAYER, get_country,
                                              get_organization_type, get_when)
from websecmap.organizations.models import Organization, Promise

log = logging.getLogger(__package__)


def get_organization_report_by_name(country: str = DEFAULT_COUNTRY, organization_type=DEFAULT_LAYER,
                                    organization_name=None, weeks_back=0):

    organization = Organization.objects.filter(
        name__iexact=organization_name,
        country=get_country(country),
        type=get_organization_type(organization_type),
        is_dead=False
    ).first()

    log.debug("%s %s %s " % (organization_name, get_country(country), get_organization_type(organization_type)))

    if not organization:
        return {}

    return get_organization_report_by_id(organization.pk, weeks_back)


def get_organization_report_by_id(organization_id: int, weeks_back: int = 0):
    # todo: check if the organization / layer is displayed on the map.

    when = get_when(weeks_back)

    organization = Organization.objects.all().filter(pk=organization_id)
    if not organization:
        return {}

    ratings = organization.filter(organizationreport__when__lte=when)
    values = ratings.values(
        'organizationreport__calculation',
        'organizationreport__when',
        'name',
        'pk',
        'twitter_handle',
        'organizationreport__high',
        'organizationreport__medium',
        'organizationreport__low'
    ).latest('organizationreport__when')

    # get the most recent non-expired 'promise'
    promise = get_last_promise(organization_id)

    report = {
        "name": values['name'],
        "slug": slugify(values['name']),
        "id": values['pk'],
        "twitter_handle": values['twitter_handle'],
        "when": values['organizationreport__when'].isoformat(),

        # fixing json being presented and escaped as a string, this makes it a lot slowr
        # had to do this cause we use jsonfield, not django_jsonfield, due to rendering map widgets in admin
        "calculation": json.loads(values['organizationreport__calculation']),
        "promise": promise,
        "high": values['organizationreport__high'],
        "medium": values['organizationreport__medium'],
        "low": values['organizationreport__low'],
    }

    return report


def get_last_promise(organization_id):

    promise = Promise.objects.filter(organization_id=organization_id, expires_on__gt=timezone.now())
    promise = promise.order_by('-expires_on')
    promise = promise.values('created_on', 'expires_on')
    return promise.first()
