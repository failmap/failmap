from datetime import date, datetime, timedelta, timezone

import re
import iso3166
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


REMARK = "Get the code and all data from our gitlab repo: https://gitlab.com/internet-cleanup-foundation/"
DEFAULT_COUNTRY = "NL"
DEFAULT_LAYER = "municipality"


def get_organization_type(name: str) -> int:
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

    my_list = []
    for conf in confs:
        if conf not in my_list:
            my_list.append(conf)

    return my_list


def get_layers(country: str = "NL"):
    layers = (
        Configuration.objects.all()
        .filter(country=get_country(country), is_displayed=True)
        .order_by("display_order")
        .values_list("organization_type__name", flat=True)
    )

    return list(layers)


def get_when(days_back: int) -> datetime:
    if not days_back:
        return datetime.now(timezone.utc)

    return datetime.now(timezone.utc) - relativedelta(days=int(days_back))


def determine_when(days_back: int = 0, at_date: date = None) -> datetime:
    # Possible to go back some days from now.
    # Possible to specify a specific date
    # Possible to specify a number of days back from a specific date
    some_date = at_date or datetime.now(timezone.utc).date()

    # Use the max time of that day. Because if you want to see a report of January 20th, you dont want to see
    # the report of things less than january 20th 00:00, but less then january 20th 23:59:59
    # so here we'll just add 1 day and subtract 1 microsecond to get the last possible moment for a day
    some_date_with_time = datetime(year=some_date.year, month=some_date.month, day=some_date.day)
    some_date_with_time = some_date_with_time + timedelta(days=1) - timedelta(microseconds=1)

    return some_date_with_time - relativedelta(days=days_back)


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
