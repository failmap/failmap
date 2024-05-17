import logging
from typing import Callable, List

from django.db.models import Q

from websecmap.organizations.models import Organization, Url
from websecmap.scanners import init_dict, plannedscan
from websecmap.scanners.models import Endpoint
from websecmap.scanners.scanner.__init__ import (
    allowed_to_scan,
    endpoint_filters,
    q_configurations_to_scan,
    unique_and_random,
    url_filters,
)

log = logging.getLogger(__name__)


# this one is special, it can filter on all levels, but it will make sure that the result is only a top level.
def filter_top_level_domains(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> List[Url]:
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    # DNSSEC only works on top level urls

    # gather urls from organizations
    if organizations_filter:
        organizations = Organization.objects.filter(**organizations_filter).only("id")
        urls = Url.objects.filter(
            q_configurations_to_scan(),
            Q(computed_subdomain__isnull=True) | Q(computed_subdomain=""),
            organization__in=organizations,
            is_dead=False,
            **urls_filter,
        )
    elif endpoints_filter:
        # and now retrieve urls from endpoints
        endpoints = Endpoint.objects.filter(**endpoints_filter).only("id")
        urls = Url.objects.filter(
            q_configurations_to_scan(),
            Q(computed_subdomain__isnull=True) | Q(computed_subdomain=""),
            is_dead=False,
            endpoint__in=endpoints,
            **urls_filter,
        )
    else:
        # now urls directly
        urls = Url.objects.filter(
            q_configurations_to_scan(),
            Q(computed_subdomain__isnull=True) | Q(computed_subdomain=""),
            is_dead=False,
            **urls_filter,
        )

    # retrieve a minimal amount of data:
    urls = urls.only("id", "url")

    # Optimize: only required values, unique and randomized
    urls = unique_and_random(urls)

    log.debug("Filtering top level domains resulten in %s urls", len(urls))
    return urls


def filter_endpoints_only(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> List[Url]:
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    endpoints = Endpoint.objects.all()
    endpoints = endpoints.filter(q_configurations_to_scan(level="endpoint"))
    endpoints = endpoint_filters(endpoints, organizations_filter, urls_filter, endpoints_filter)
    endpoints = endpoints.only("id", "url__url")
    endpoints = unique_and_random(endpoints)
    return unique_and_random([endpoint.url for endpoint in endpoints])


def filter_endpoints_only_as_endpoints(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> List[Endpoint]:
    # this is a copy of the filter_endpoints_only which is usually creating an extra layer of work as the urls
    # then will again be filtered to endpoints.
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    endpoints = Endpoint.objects.all()
    endpoints = endpoints.filter(q_configurations_to_scan(level="endpoint"))
    endpoints = endpoint_filters(endpoints, organizations_filter, urls_filter, endpoints_filter)
    endpoints = endpoints.only("id", "url__url", "port", "protocol", "ip_version")
    endpoints = unique_and_random(endpoints)
    return unique_and_random(endpoints)


def filter_urls_only(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> List[Url]:
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    urls = Url.objects.all().filter(q_configurations_to_scan(level="url"), not_resolvable=False, is_dead=False)
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter)
    urls = urls.only("id", "url")

    return unique_and_random(urls)


def apply_organzation_or_endpoint_filter_before_url_filter(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
):
    # ignore administratively dead domains by default.

    # always applies the URL filter after filtering organizations or endpoints.
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)

    if organizations_filter:
        organizations = Organization.objects.filter(**organizations_filter).only("id")
        log.info("Organization filter applied with %s organizations.", len(organizations))
        urls = Url.objects.filter(q_configurations_to_scan(), organization__in=organizations, **urls_filter)
    elif endpoints_filter:
        endpoints = Endpoint.objects.filter(**endpoints_filter).only("id")
        log.info("Endpoint filter applied with %s endpoints.", len(endpoints))
        urls = Url.objects.filter(q_configurations_to_scan(), endpoint__in=endpoints, **urls_filter)
    else:
        urls = Url.objects.filter(q_configurations_to_scan(), **urls_filter)

    # retrieve a minimal amount of data:
    urls = urls.only("id", "url")

    # make sure all urls are unique (some are shared between organizations, or a custom query might dupe them)
    urls = unique_and_random(urls)
    log.info("Discovering HTTP endpoints for %s urls.", len(urls))

    return urls


def generic_plan_scan(
    scanner_name: str = "",
    activity: str = "scan",
    filter_method: Callable = None,
    organizations_filter: dict = None,
    urls_filter: dict = None,
    endpoints_filter: dict = None,
    **kwargs,
):
    if not allowed_to_scan(scanner_name, activity):
        log.debug("Not allowed to perform %s with scanner %s.", activity, scanner_name)
        return []

    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    urls = filter_method(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    log.info("Creating '%s' '%s' task for %s urls.", scanner_name, activity, len(urls))
    plannedscan.request(activity=activity, scanner=scanner_name, urls=urls)


def merge_endpoints_filter(some_filter=None, **kwargs):
    if not some_filter:
        return kwargs

    # the order is relevant, the latter may overwrite the first
    kwargs["endpoints_filter"] = {**kwargs.get("endpoints_filter", {}), **some_filter}
    return kwargs


def merge_urls_filter(some_filter=None, **kwargs):
    if not some_filter:
        return kwargs

    kwargs["urls_filter"] = {**kwargs.get("urls_filter", {}), **some_filter}
    return kwargs


def merge_organizations_filter(some_filter=None, **kwargs):
    if not some_filter:
        return kwargs

    kwargs["organizations_filter"] = {**kwargs.get("organizations_filter", {}), **some_filter}
    return kwargs
