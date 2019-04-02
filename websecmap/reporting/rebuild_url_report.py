import logging

from celery import group

from websecmap.celery import Task
from websecmap.organizations.models import Url
from websecmap.reporting.report import recreate_url_reports
from websecmap.scanners.scanner import add_model_filter
from websecmap.scanners.scanner.__init__ import q_configurations_to_report

log = logging.getLogger(__package__)


def compose_task(
    **kwargs
) -> Task:

    urls = Url.objects.filter(q_configurations_to_report())
    urls = add_model_filter(urls, **kwargs)
    if not urls:
        log.error("No urls found.")
        return group()

    tasks = [recreate_url_reports.si(urls)]

    if not tasks:
        log.error("Could not rebuild reports, filters resulted in no tasks created.")
        log.debug("Url filter: %s" % kwargs)
        return group()

    log.debug("Number of tasks: %s" % len(tasks))

    task = group(tasks)

    return task
