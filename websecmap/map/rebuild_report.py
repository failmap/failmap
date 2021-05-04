import logging

from celery import group

from websecmap.celery import Task
from websecmap.map.report import recreate_organization_reports
from websecmap.organizations.models import Organization, Url
from websecmap.reporting.report import recreate_url_reports
from websecmap.scanners.scanner.__init__ import q_configurations_to_report

log = logging.getLogger(__package__)


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    """
    Compose taskset to rebuild specified organizations/urls.
    """

    if endpoints_filter:
        raise NotImplementedError("This scanner does not work on a endpoint level.")

    log.info("Organization filter: %s" % organizations_filter)
    log.info("Url filter: %s" % urls_filter)

    # Only displayed configurations are reported. Because why have reports on things you don't display?
    # apply filter to organizations (or if no filter, all organizations)
    organizations = Organization.objects.filter(q_configurations_to_report("organization"), **organizations_filter)

    log.debug("Organizations: %s" % len(organizations))

    # Create tasks for rebuilding ratings for selected organizations and urls.
    # Wheneven a url has been (re)rated the organization for that url need to
    # be (re)rated as well to propagate the result of the url rate. Tasks will
    # be created per organization to first rebuild all of this organizations
    # urls (depending on url filters) after which the organization rating will
    # be rebuild.

    tasks = []

    for organization in organizations:
        urls = Url.objects.filter(q_configurations_to_report(), organization=organization, **urls_filter)
        if not urls:
            continue

        # Do NOT update the statistics also. This can take long and might not have a desired effect.
        # those updates have to be called explicitly.
        tasks.append(recreate_url_reports.si(urls) | recreate_organization_reports.si([organization.pk]))

    if not tasks:
        log.error("Could not rebuild reports, filters resulted in no tasks created.")
        log.debug("Organization filter: %s" % organizations_filter)
        log.debug("Url filter: %s" % urls_filter)
        log.debug("urls to display: %s" % q_configurations_to_report())
        log.debug("organizatins to display: %s" % q_configurations_to_report("organization"))
        return group()

    log.debug("Number of tasks: %s" % len(tasks))

    # Given this is a complete rebuild, also rebuild the statistics for the past year. (only a year is shown max)
    # if you want to rebuild reports, just run a "calculate map data" by hand also. Code was removed here.

    task = group(tasks)

    return task
