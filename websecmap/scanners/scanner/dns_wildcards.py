import logging

from celery import Task, group

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners.scanner.subdomains import discover_wildcard, url_by_filters

log = logging.getLogger(__package__)


def compose_discover_task(organizations_filter: dict = dict(), urls_filter: dict = dict(), **kwargs) -> Task:
    urls = url_by_filters(organizations_filter=organizations_filter, urls_filter=urls_filter)
    log.info(f'Checking wildcards on {len(urls)} urls.')

    task = group(discover_wildcard.si(url.url) | store_wildcard.s(url.id) for url in urls)
    return task


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
