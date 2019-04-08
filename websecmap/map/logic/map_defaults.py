import iso3166
from constance import config
from django.http import JsonResponse

from websecmap.app.common import JSEncoder
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


def get_organization_type(name: str):
    try:
        return OrganizationType.objects.get(name=name).id
    except OrganizationType.DoesNotExist:
        default = Configuration.objects.all().filter(
            is_displayed=True, is_the_default_option=True
        ).order_by('display_order').values_list('organization_type__id', flat=True).first()

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


def get_defaults(request, ):
    data = Configuration.objects.all().filter(
        is_displayed=True,
        is_the_default_option=True
    ).order_by('display_order').values('country', 'organization_type__name').first()

    if not data:
        return JsonResponse({'country': "NL", 'layer': "municipality"}, safe=False, encoder=JSEncoder)

    return JsonResponse({'country': data['country'], 'layer': data['organization_type__name']},
                        safe=False, encoder=JSEncoder)


def get_default_country(request, ):
    country = Configuration.objects.all().filter(
        is_displayed=True,
        is_the_default_option=True
    ).order_by('display_order').values_list('country', flat=True).first()

    if not country:
        return config.PROJECT_COUNTRY

    return JsonResponse([country], safe=False, encoder=JSEncoder)


def get_default_layer(request, ):

    organization_type = Configuration.objects.all().filter(
        is_displayed=True,
        is_the_default_option=True
    ).order_by('display_order').values_list('organization_type__name', flat=True).first()

    if not organization_type:
        return 'municipality'
    # from config table
    return JsonResponse([organization_type], safe=False, encoder=JSEncoder)


def get_default_layer_for_country(request, country: str = "NL"):

    organization_type = Configuration.objects.all().filter(
        is_displayed=True,
        country=get_country(country)
    ).order_by('display_order').values_list('organization_type__name', flat=True).first()

    if not organization_type:
        return 'municipality'
    # from config table
    return JsonResponse([organization_type], safe=False, encoder=JSEncoder)


def get_countries(request,):
    # sqllite doens't do distinct on, workaround

    confs = Configuration.objects.all().filter(
        is_displayed=True).order_by('display_order').values_list('country', flat=True)

    list = []
    for conf in confs:
        if conf not in list:
            list.append(conf)

    return JsonResponse(list, safe=False, encoder=JSEncoder)


def get_layers(request, country: str = "NL"):

    layers = Configuration.objects.all().filter(
        country=get_country(country),
        is_displayed=True
    ).order_by('display_order').values_list('organization_type__name', flat=True)

    return JsonResponse(list(layers), safe=False, encoder=JSEncoder)
