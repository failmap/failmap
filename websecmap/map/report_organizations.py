import logging

from celery import group
from django.db.models import Count

from websecmap.celery import Task
from websecmap.map.report import create_organization_reports_now, default_organization_rating
from websecmap.organizations.models import Organization, Url
from websecmap.scanners import init_dict
from websecmap.scanners.scanner.__init__ import q_configurations_to_report

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
    # todo: organizations that have no endpoints could get a default rating, which is much quicker
    #  than iterating all organizations. But it does not save too much time...
    urls = (
        Url.objects.filter(q_configurations_to_report(), organization__in=organization_ids, **urls_filter)
        .annotate(n_endpoints=Count("endpoint"))
        .filter(n_endpoints__gt=0)
        .only("id", "organization__id")
        .values("id", "organization__id")
    )
    organizations_with_urls = {url["organization__id"] for url in urls}
    organizations_without_urls = set(organization_ids) - organizations_with_urls

    # can still add an empty organization rating even though there is nothing to show.
    # Will create an empty gray region.
    if list(organizations_without_urls):
        # warning: default_organization_rating has a side effect, it will rate everything if nothing is given...
        tasks.append(default_organization_rating.si(list(organizations_without_urls)))

    tasks.extend(create_organization_reports_now.si([organization_id]) for organization_id in organizations_with_urls)
    return group(tasks)
