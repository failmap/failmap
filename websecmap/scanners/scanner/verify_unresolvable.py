import logging

from celery import Task, group

from websecmap.celery import app
from websecmap.scanners import plannedscan
from websecmap.scanners.scanner import subdomains

log = logging.getLogger(__package__)


@app.task(queue="storage")
def plan_verify(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
):
    urls = filter_verify(organizations_filter, urls_filter, **kwargs)
    plannedscan.request(activity="verify", scanner="verify_unresolvable", urls=urls)


@app.task(queue="storage")
def compose_planned_verify_task(**kwargs):
    urls = plannedscan.pickup(activity="verify", scanner="verify_unresolvable", amount=kwargs.get("amount", 25))
    return compose_verify_task(urls)


def filter_verify(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
):
    override_filter = {"not_resolvable": True}
    urls_filter = {**urls_filter, **override_filter}

    return subdomains.filter_verify(organizations_filter, urls_filter, **kwargs)


def compose_manual_verify_task(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
):
    urls = filter_verify(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    return compose_verify_task(urls)


def compose_verify_task(urls) -> Task:
    task = group(
        subdomains.url_resolves.si(url.url)
        | subdomains.handle_resolves.s(url)
        | plannedscan.finish.si("verify", "verify_unresolvable", url)
        for url in urls
    )
    return task
