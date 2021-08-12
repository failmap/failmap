# Generic functions for scanners
import logging
import random
from typing import List

from constance import config
from django.db.models import Q

from websecmap.map.models import Configuration
from websecmap.organizations.models import Organization, Url
from websecmap.scanners import plannedscan
from websecmap.scanners.models import Endpoint, EndpointGenericScan

log = logging.getLogger(__name__)


def add_model_filter(queryset, **kwargs):
    """
    Allows you to create whatever (!) filter you want. Including the possibility to compare password fields, so make
    no untrusted user input is handled in this function.

    Aside from that, it gives you great power. It allows you to filter on your model, using the following syntax:
    filter = {'MODELNAME_filter': {[ANY FILTER HERE]}}

    To filter accounts for the account name test:
    filter = {'account_filter': {'name': 'test'}}

    The filter can deliver cartesian products. And the filter does not 'exclude' things.

    Note that with this kind of filtering, users can retrieve passwords and other sensitive fields. For example
    with comparing to the text / hash value. So while this is a really convenient function, don't give users
    access to this function.

    :param queryset:
    :param kwargs:
    :return:
    """

    # we expect a Object_filters in kwargs in order for it to work.
    # dashboard.internet_nl_dashboard.models.Account
    # This is probably one of the ugliest ways to do this :)
    model_filters = str(queryset.model).replace("'>", "").split(".")[-1].lower() + "_filters"
    log.debug("Checking for filters: %s" % model_filters)

    if kwargs.get(model_filters, None):
        filters = kwargs.get(model_filters)
        log.debug("Filtering on: %s" % filters)
        queryset = queryset.filter(**filters)

    return queryset


# The reason these permissions are taken away from the rest of the implementation is to
# make sure these permissions can be more easily be replaced by other permissions. For example we might want to
# drop constance in favor of a better, more shiny, interface when possible.


# simply matching config variables to modules.
# Note that .__module__  is always celery.local :)
def allowed_to_scan(scanner_name: str = ""):

    if not config.SCAN_AT_ALL:
        return False

    if scanner_name == "dummy":
        return True

    try:
        return getattr(config, "USE_SCANNER_%s" % scanner_name.upper())
    except AttributeError:
        log.debug("Scanner %s is not allowed to scan due to setting." % scanner_name)
        return False


def allowed_to_discover_urls(scanner_name: str = ""):
    try:
        return getattr(config, "DISCOVER_URLS_USING_%s" % scanner_name.upper())
    except AttributeError:
        log.debug("Scanner %s is not allowed to discover urls due to setting." % scanner_name)
        return False


def allowed_to_discover_endpoints(scanner_name: str = ""):
    try:
        return getattr(config, "DISCOVER_ENDPOINTS_USING_%s" % scanner_name.upper())
    except AttributeError:
        log.debug("Scanner %s is not allowed to discover endpoints due to setting." % scanner_name)
        return False


def q_configurations_to_scan(level: str = "url"):
    """
    Retrieves configurations and makes q-queries for them. You can select if you want to have the q-queries directly
    for the organization tables, or with a join from url to organization.

    To evaluate: This is a quick fix, the organization might refer to configuration in the future?

    Will be skipped if there are no organizations / countries. Which helps adoption in projects that don't use
    these concepts.

    :param level:
    :return:
    """
    configurations = list(Configuration.objects.all().filter(is_scanned=True).values("country", "organization_type"))
    if not configurations:
        log.debug("No scanning configuration defined, not filtering.")
        return Q()

    # log.debug('Adding %s level configurations: %s' % (level, configurations))

    qs = Q()

    if level == "organization":
        for configuration in configurations:
            qs.add(Q(type=configuration["organization_type"], country=configuration["country"]), Q.OR)

    if level == "url":
        for configuration in configurations:
            qs.add(
                Q(
                    organization__type=configuration["organization_type"],
                    organization__country=configuration["country"],
                ),
                Q.OR,
            )

    if level == "endpoint":
        for configuration in configurations:
            qs.add(
                Q(
                    url__organization__type=configuration["organization_type"],
                    url__organization__country=configuration["country"],
                ),
                Q.OR,
            )

    return qs


def q_configurations_to_report(level: str = "url"):
    """
    Retrieves configurations and makes q-queries for them. You can select if you want to have the q-queries directly
    for the organization tables, or with a join from url to organization.

    To evaluate: This is a quick fix, the organization might refer to configuration in the future?

    An emtpy set means EVERYTHING will be reported.

    :param level:
    :return:
    """
    configurations = list(Configuration.objects.all().filter(is_reported=True).values("country", "organization_type"))
    qs = Q()

    if level == "organization":
        for configuration in configurations:
            qs.add(Q(type=configuration["organization_type"], country=configuration["country"]), Q.OR)

    if level == "url":
        for configuration in configurations:
            qs.add(
                Q(
                    organization__type=configuration["organization_type"],
                    organization__country=configuration["country"],
                ),
                Q.OR,
            )

    return qs


def q_configurations_to_display(level: str = "url"):
    """
    Retrieves configurations and makes q-queries for them. You can select if you want to have the q-queries directly
    for the organization tables, or with a join from url to organization.

    To evaluate: This is a quick fix, the organization might refer to configuration in the future?

    :param level:
    :return:
    """
    configurations = list(Configuration.objects.all().filter(is_displayed=True).values("country", "organization_type"))
    qs = Q()

    if level == "organization":
        for configuration in configurations:
            qs.add(Q(type=configuration["organization_type"], country=configuration["country"]), Q.OR)

    if level == "url":
        for configuration in configurations:
            qs.add(
                Q(
                    organization__type=configuration["organization_type"],
                    organization__country=configuration["country"],
                ),
                Q.OR,
            )

    return qs


def endpoint_filters(query, organizations_filter, urls_filter, endpoints_filter):
    if organizations_filter:
        organizations = Organization.objects.filter(**organizations_filter)
        query = query.filter(url__organization__in=organizations)

    if endpoints_filter:
        endpoints = Endpoint.objects.filter(**endpoints_filter)
        query = query.filter(pk__in=endpoints)

    if urls_filter:
        urls = Url.objects.filter(**urls_filter)
        query = query.filter(url__in=urls)

    return query


# todo: the __in filter is not optimal. What is the real approach we want? Probably the original approach, but that
# didn't work.
def url_filters(query, organizations_filter, urls_filter, endpoints_filter):
    if organizations_filter:
        organizations = Organization.objects.filter(**organizations_filter)
        query = query.filter(organization__in=organizations)

    if endpoints_filter:
        endpoints = Endpoint.objects.filter(**endpoints_filter)
        query = query.filter(endpoint__in=endpoints)  # warning: cartesian product!

    if urls_filter:
        urls = Url.objects.filter(**urls_filter)
        query = query.filter(pk__in=urls)

    return query


# https://chrisalbon.com/python/data_wrangling/break_list_into_chunks_of_equal_size/
# Create a function called "chunks" with two arguments, l and n: list and number_of_desired_items
# function could not be named chunks, as that is a reserved word or something.
def chunks2(my_list, n):
    # For item i in a range that is a length of l,
    for i in range(0, len(my_list), n):
        # Create an index range for l of n items:
        yield my_list[i : i + n]


def unique_and_random(items: List):
    items = list(set(items))
    random.shuffle(items)
    return items


def finish_those_that_wont_be_scanned(scanner: str, scans: List[EndpointGenericScan], urls: List[Url]):
    """
    Some urls might be requested for a scan but are not eligible anymore because, for example, the
    endpoint already has been explained. Once a scan on a url is requested, it will be retried until the
    end of time. With this routine stuff that will not be scanned (missing in going_to_be_scanned) will
    be set to finished.
    Uses in autoexplain methods, where sometimes explanations are not needed or the query
    """
    all_url_ids = [url.id for url in urls]
    log.debug(f"All url ids: {all_url_ids}.")
    scanned_url_ids = [epgs.endpoint.url.id for epgs in scans]
    log.debug(f"Will not be scanned: {all_url_ids}.")
    will_not_be_scanned = list(set(all_url_ids) - set(scanned_url_ids))
    for not_scanned_id in will_not_be_scanned:
        log.debug(f"Not going to scan {not_scanned_id}, as there is nothing to scan for this url anymore.")
        plannedscan.finish("scan", scanner, not_scanned_id)
