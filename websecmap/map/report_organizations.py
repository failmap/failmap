import logging


from celery import group
from django.db.models import Count

from websecmap.celery import Task
from websecmap.organizations.models import Organization, Url

from websecmap.scanners import init_dict
from websecmap.scanners.scanner.__init__ import q_configurations_to_report

from websecmap.map.report import create_organization_reports_now

log = logging.getLogger(__package__)


def compose_task(
    organizations_filter: dict = None,
    urls_filter: dict = None,
    endpoints_filter: dict = None,
) -> Task:
    # for rationale, see compose_task in report.py
    organizations_filter, urls_filter, endpoints_filter = init_dict(organizations_filter, urls_filter, endpoints_filter)

    if endpoints_filter:
        raise NotImplementedError("This scanner does not work on a endpoint level.")

    organization_ids = Organization.objects.filter(
        q_configurations_to_report("organization"),
        is_dead=False,
        **organizations_filter,
    ).values_list("id", flat=True)

    # make sure they are unique
    organization_ids = list(set(organization_ids))
    log.debug("Organizations: %s", len(organization_ids))

    tasks = []
    urls = (
        Url.objects.filter(q_configurations_to_report(), organization__in=organization_ids, **urls_filter)
        .annotate(n_endpoints=Count("endpoint"))
        .filter(n_endpoints__gt=0)
        .only("id", "organization__id")
        .values("id", "organization__id")
    )
    organizations_with_urls = {url["organization__id"] for url in urls}
    tasks.extend(create_organization_reports_now.si([organization_id]) for organization_id in organizations_with_urls)
    return group(tasks)
