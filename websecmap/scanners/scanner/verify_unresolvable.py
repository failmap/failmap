import logging

from celery import Task

from websecmap.scanners.scanner.subdomains import \
    compose_verify_task as subdomain_compose_verify_task

log = logging.getLogger(__package__)


def compose_verify_task(organizations_filter: dict = dict(),
                        urls_filter: dict = dict(),
                        endpoints_filter: dict = dict(), **kwargs) -> Task:

    override_filter = {"not_resolvable": True}
    urls_filter = {**urls_filter, **override_filter}

    return subdomain_compose_verify_task(organizations_filter=organizations_filter,
                                         urls_filter=urls_filter)
