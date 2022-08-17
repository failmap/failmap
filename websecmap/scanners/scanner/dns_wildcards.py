import logging

from celery import Task, group

from websecmap.celery import EXPIRES_IN_ONE_DAY, app
from websecmap.organizations.models import Url
from websecmap.scanners import init_dict, plannedscan
from websecmap.scanners.scanner import unique_and_random
from websecmap.scanners.scanner.subdomains import discover_wildcard, url_by_filters

log = logging.getLogger(__package__)


def filter_discover(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
):
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    urls = url_by_filters(organizations_filter=organizations_filter, urls_filter=urls_filter)
    return unique_and_random(urls)


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def compose_planned_discover_task(**kwargs):
    urls = plannedscan.pickup(activity="discover", scanner="dns_wildcards", amount=kwargs.get("amount", 200))
    return compose_discover_task(urls)


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def plan_discover(organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs):
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    urls = filter_discover(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    plannedscan.request(activity="discover", scanner="dns_wildcards", urls=urls)


def compose_discover_task(urls):
    task = group(
        discover_wildcard.si(url.url)
        | store_wildcard.s(url.id)
        | plannedscan.finish.si("discover", "dns_wildcards", url.pk)
        for url in urls
    )
    return task


def compose_manual_discover_task(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> Task:
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)
    urls = filter_discover(organizations_filter, urls_filter, endpoints_filter, **kwargs)

    # a heuristic
    if not urls:
        log.info("Did not get any urls to discover wildcards.")
        return group()

    log.debug("Going to scan for wildcards for the following %s urls.", len(urls))

    return compose_discover_task(urls)


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def store_wildcard(result: bool, url_id: int):
    try:
        url = Url.objects.all().get(id=url_id)
    except Url.DoesNotExist:
        log.debug("Url %s does not exist anymore. Not doing anything", url_id)
        return

    # see if we need to do anything, if not, that saves a database operation. Reading is faster than writing.
    if url.uses_dns_wildcard and result:
        log.debug("No change in wildcard result on %s. Wildcard stays enabled.", url)
        return

    if not url.uses_dns_wildcard and not result:
        log.debug("No change in wildcard result on %s. Wildcard stays disabled.", url)
        return

    if result:
        log.debug("Wildcard discovered on %s.", url)
        url.uses_dns_wildcard = True
        url.save()
    else:
        log.debug("Wildcard removed on %s.", url)
        url.uses_dns_wildcard = False
        url.save()
