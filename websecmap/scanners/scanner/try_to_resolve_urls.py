import logging

from celery import Task, group

from websecmap.organizations.models import Url
from websecmap.scanners.scanner.dns import handle_resolves, url_resolves
from websecmap.scanners.scanner.scanner import q_configurations_to_scan, url_filters

log = logging.getLogger(__package__)


def compose_verify_task(organizations_filter: dict = dict(),
                        urls_filter: dict = dict(),
                        endpoints_filter: dict = dict(), **kwargs) -> Task:

    # instead of only checking by domain, just accept the filters as they are handled in any other scenario...

    # default_filter = {"not_resolvable": True}
    # if you just want to verify all existing, try verify dns/subdomains....
    default_filter = {}
    urls_filter = {**urls_filter, **default_filter}

    urls = Url.objects.all().filter(q_configurations_to_scan(level='url'))
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter)

    if not urls:
        log.debug('No urls found for (sub)domain verification.')

    log.info("Will verify DNS resolvability of %s urls" % len(urls))

    task = group(url_resolves.si(url) | handle_resolves.s(url) for url in urls)
    return task
