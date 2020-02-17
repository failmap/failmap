import csv
import logging
from io import StringIO

from django.db.models import Q

from websecmap.map.logic.map_defaults import get_country, get_organization_type
from websecmap.map.models import Configuration
from websecmap.organizations.models import Url

log = logging.getLogger(__package__)


def get_map_configuration():
    # Using this, it's possible to get the right params for 2ndlevel domains

    configs = Configuration.objects.all().filter(
        is_displayed=True,
        is_the_default_option=True
    ).order_by('display_order')

    data = []
    for config in configs:
        data.append({'country': config.country.code, 'layer': config.organization_type.name})

    return data


def get_2ndlevel_domains(country, layer):
    urls = Url.objects.all().filter(
        Q(computed_subdomain__isnull=True) | Q(computed_subdomain=""),
        organization__country=get_country(country),
        organization__type=get_organization_type(layer)
    ).values_list('url', flat=True)

    urls = list(set(urls))

    return urls


def remove_last_dot(my_text):
    return my_text[0:len(my_text)-1] if my_text[len(my_text)-1:len(my_text)] == "." else my_text


def sidn_domain_upload(csv_data):
    """
    If the domain exists in the db, any subdomain will be added.
    As per usual, adding a subdomain will check if the domain is valid and resolvable.

    Format:
    ,2ndlevel,qname,distinct_asns
    *censored number*,arnhem.nl.,*.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,01.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,sdfg.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,03.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,04www.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,sdfgs.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,10.255.254.35www.arnhem.nl.,*censored number*
    *censored number*,arnhem.nl.,12.arnhem.nl.,*censored number*
    :return:
    """

    f = StringIO(csv_data)
    reader = csv.reader(f, delimiter=',')
    added = []

    for row in reader:

        if len(row) < 4:
            continue

        existing_second_level_url = Url.objects.all().filter(
            Q(computed_subdomain__isnull=True) | Q(computed_subdomain=""),
            url=remove_last_dot(row[1]), is_dead=False
        ).first()

        if not existing_second_level_url:
            log.debug(f"Url {remove_last_dot(row[1])} is not in the database yet, so cannot add a subdomain.")
            continue

        new_subdomain = remove_last_dot(row[2])
        # the entire domain is included:
        new_subdomain = new_subdomain[0:len(new_subdomain) - len(row[1])]

        has_been_added = existing_second_level_url.add_subdomain(new_subdomain)
        if has_been_added:
            added.append(has_been_added)

    return added
