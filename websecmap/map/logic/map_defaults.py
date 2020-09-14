from datetime import datetime

import iso3166
import pytz
from constance import config
from dateutil.relativedelta import relativedelta

from websecmap.map.models import Configuration
from websecmap.organizations.models import Organization, OrganizationType

# This list changes roughly every second, but that's not our problem anymore.
COUNTRIES = iso3166.countries_by_alpha2

# even while this might be a bit expensive (caching helps), it still is more helpful then
# defining everything by hand.


# any two letters will do... :)
# All countries are managed by django-countries, but we're fine with any other weird stuff.
# url routing does validation... expect it will go wrong so STILL do validation...


# note: this is only visual, this is no security mechanism(!) Don't act like it is.
# the data in this system is as open as possible.


remark = "Get the code and all data from our gitlab repo: https://gitlab.com/internet-cleanup-foundation/"
DEFAULT_COUNTRY = "NL"
DEFAULT_LAYER = "municipality"


def get_organization_type(name: str):
    try:
        return OrganizationType.objects.get(name=name).id
    except OrganizationType.DoesNotExist:
        default = (
            Configuration.objects.all()
            .filter(is_displayed=True, is_the_default_option=True)
            .order_by("display_order")
            .values_list("organization_type__id", flat=True)
            .first()
        )

        return default if default else 1


def get_country(code: str):
    import re

    # existing countries. Yes, you can add fictional countries if you would like to, that will be handled below.
    if code in COUNTRIES:
        return code

    match = re.search(r"[A-Z]{2}", code)
    if not match:
        # https://what-if.xkcd.com/53/
        return config.PROJECT_COUNTRY

    # check if we have a country like that in the db:
    if not Organization.objects.all().filter(country=code).exists():
        return config.PROJECT_COUNTRY

    return code


def get_defaults():
    data = (
        Configuration.objects.all()
        .filter(is_displayed=True, is_the_default_option=True)
        .order_by("display_order")
        .values("country", "organization_type__name")
        .first()
    )

    if not data:
        return {"country": DEFAULT_COUNTRY, "layer": DEFAULT_LAYER}

    return {"country": data["country"], "layer": data["organization_type__name"]}


def get_default_country():
    country = (
        Configuration.objects.all()
        .filter(is_displayed=True, is_the_default_option=True)
        .order_by("display_order")
        .values_list("country", flat=True)
        .first()
    )

    if not country:
        return [config.PROJECT_COUNTRY]

    return [country]


def get_default_layer():

    organization_type = (
        Configuration.objects.all()
        .filter(is_displayed=True, is_the_default_option=True)
        .order_by("display_order")
        .values_list("organization_type__name", flat=True)
        .first()
    )

    if not organization_type:
        return [DEFAULT_LAYER]

    return [organization_type]


def get_default_layer_for_country(country: str = "NL"):

    organization_type = (
        Configuration.objects.all()
        .filter(is_displayed=True, country=get_country(country))
        .order_by("display_order")
        .values_list("organization_type__name", flat=True)
        .first()
    )

    if not organization_type:
        return [DEFAULT_LAYER]
    # from config table

    return [organization_type]


def get_countries():
    # sqllite doens't do distinct on, workaround

    confs = (
        Configuration.objects.all()
        .filter(is_displayed=True)
        .order_by("display_order")
        .values_list("country", flat=True)
    )

    list = []
    for conf in confs:
        if conf not in list:
            list.append(conf)

    return list


def get_layers(country: str = "NL"):

    layers = (
        Configuration.objects.all()
        .filter(country=get_country(country), is_displayed=True)
        .order_by("display_order")
        .values_list("organization_type__name", flat=True)
    )

    return list(layers)


def get_when(weeks_back):
    if not weeks_back:
        return datetime.now(pytz.utc)
    else:
        return datetime.now(pytz.utc) - relativedelta(weeks=int(weeks_back))


def get_initial_countries():
    """
    # save a query and a bunch of translation issues (django countries contains all countries in every language
    # so we don't have to find a javascript library to properly render...
    # the downside is that we have to run a query every load, and do less with javascript. Upside is that
    # it renders faster and easier.

    :return:
    """
    confs = (
        Configuration.objects.all()
        .filter(is_displayed=True)
        .order_by("display_order")
        .values_list("country", flat=True)
    )

    inital_countries = []
    for conf in confs:
        if conf not in inital_countries:
            inital_countries.append(conf)

    return inital_countries


def organizationtype_exists(organization_type_name):
    if OrganizationType.objects.filter(name=organization_type_name).first():
        return {"set": True}

    return {"set": False}
