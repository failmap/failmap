"""
This is only forward syncing. We cannot / will not delete urls automatically.
"""

import logging

from celery import group

from failmap.celery import Task, app
from failmap.organizations.models import Url
from failmap.pro.models import FailmapOrganizationDataFeed, UrlDataFeed

log = logging.getLogger(__package__)


def compose_task(organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(),
                 ) -> Task:
    feeds = FailmapOrganizationDataFeed.objects.all()
    tasks = [sync_failmap_datafeed.si(feed) for feed in feeds]

    feeds = UrlDataFeed.objects.all()
    tasks += [sync_subdomain_datafeed.si(feed) for feed in feeds]

    return group(tasks)


@app.task(queue='storage')
def sync_failmap_datafeed(failmapOrganizationDataFeed: FailmapOrganizationDataFeed):
    # we cannot use _in queries as the resultset may be too large. So we have to use a stupid and simple approach that
    # is slower but works.

    urls_on_map = Url.objects.all().filter(organization=failmapOrganizationDataFeed.organization)
    urllists = failmapOrganizationDataFeed.urllist.all()

    for url_on_map in urls_on_map:
        for urllist in urllists:
            if not urllist.urls.all().filter(url=url_on_map).exists():
                urllist.urls.add(url_on_map)
                urllist.save()


@app.task(queue='storage')
def sync_subdomain_datafeed(urlDataFeed: UrlDataFeed):
    # we cannot use _in queries as the resultset may be too large. So we have to use a stupid and simple approach that
    # is slower but works.

    urls = Url.objects.all()

    if urlDataFeed.subdomain:
        urls = urls.filter(computed_subdomain__iexact=urlDataFeed.subdomain)

    if urlDataFeed.domain:
        urls = urls.filter(computed_domain__iexact=urlDataFeed.domain)

    if urlDataFeed.topleveldomain:
        urls = urls.filter(computed_suffix__iexact=urlDataFeed.topleveldomain)

    urllists = urlDataFeed.urllist.all()
    for url in urls:
        for urllist in urllists:
            if not urllist.urls.all().filter(url=url).exists():
                urllist.urls.add(url)
                urllist.save()
