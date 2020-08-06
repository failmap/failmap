import logging

from celery import Task, group

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners import plannedscan
from websecmap.scanners.scanner import unique_and_random
from websecmap.scanners.scanner.subdomains import discover_wildcard, url_by_filters

log = logging.getLogger(__package__)


def filter_discover(organizations_filter: dict = dict(),
                    urls_filter: dict = dict(),
                    endpoints_filter: dict = dict(),
                    **kwargs):
    urls = url_by_filters(organizations_filter=organizations_filter, urls_filter=urls_filter)
    return unique_and_random(urls)


@app.task(queue='storage')
def compose_planned_discover_task(**kwargs):
    urls = plannedscan.pickup(activity="discover", scanner="dns_wildcard", amount=kwargs.get('amount', 200))
    return compose_discover_task(urls)


@app.task(queue='storage')
def plan_discover(organizations_filter: dict = dict(),
                  urls_filter: dict = dict(),
                  endpoints_filter: dict = dict(),
                  **kwargs):
    urls = filter_discover(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    plannedscan.request(activity="discover", scanner="dns_wildcard", urls=urls)


def compose_discover_task(urls):
    task = group(discover_wildcard.si(url.url) | store_wildcard.s(url.id) for url in urls)
    return task


def compose_manual_discover_task(organizations_filter: dict = dict(),
                                 urls_filter: dict = dict(),
                                 endpoints_filter: dict = dict(), **kwargs) -> Task:
    urls = filter_discover(organizations_filter, urls_filter, endpoints_filter, **kwargs)

    # a heuristic
    if not urls:
        log.info("Did not get any urls to discover wildcards.")
        return group()

    log.debug("Going to scan for wildcards for the following %s urls." % len(urls))

    return compose_discover_task(urls)


@app.task(queue="storage")
def store_wildcard(result: bool, url_id: int):
    try:
        url = Url.objects.all().get(id=url_id)
    except Url.DoesNotExist:
        log.debug(f"Url {url_id} does not exist anymore. Not doing anything")
        return

    # see if we need to do anything, if not, that saves a database operation. Reading is faster than writing.
    if url.uses_dns_wildcard and result:
        log.debug(f"No change in wildcard result on {url}. Wildcard stays enabled.")
        return

    if not url.uses_dns_wildcard and not result:
        log.debug(f"No change in wildcard result on {url}. Wildcard stays disabled.")
        return

    if result:
        log.debug(f"Wildcard discovered on {url}.")
        url.uses_dns_wildcard = True
        url.save()
    else:
        log.debug(f"Wildcard removed on {url}.")
        url.uses_dns_wildcard = False
        url.save()
