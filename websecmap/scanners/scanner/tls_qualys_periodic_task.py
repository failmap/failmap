"""
A version of the qualys scanner that can handle the periodic tasks correctly.

It can handle the exclude_urls_scanned_in_the_last_n_days argument, as well as the other arguments.

basically it allows for more frequent scanning on bad urls, and less frequent on the good ones...

All the good stuff, scanned less frequently:
{
    "exclude_urls_scanned_in_the_last_n_days": 3,
    "urls_filter": {
        "endpoint__endpointgenericscan__rating__in": ["A", "A+", "A-", "trusted"]
    }
}

All the bad stuff, scanned more frequently:
{
    "exclude_urls_scanned_in_the_last_n_days": 3,
    "urls_filter": {
        "endpoint__endpointgenericscan__rating__in": ["B", "C", "F", "not trusted"]
    }
}

This query has been tested, and results in outdated stuff with bad ratings:
urls = Url.objects.filter(
    q_configurations_to_scan(),
    is_dead=False,
    not_resolvable=False,
    endpoint__protocol="https",
    endpoint__port=443,
    endpoint__is_dead=False,
    endpoint__endpointgenericscan__is_the_latest_scan=True,
    endpoint__endpointgenericscan__rating__in=['C', 'D', 'F', 'not trusted'],
    endpoint__endpointgenericscan__last_scan_moment__lte=datetime.now(tz=pytz.utc) - timedelta(days=3),
).order_by('-endpoint__endpointgenericscan__latest_scan_moment')

The query generated from the periodic task and the one running on the server are identical.

The exclude could not be placed in a separate clause, as that would not filter on the previous set. So we've
included it in the original query.

For more documentation, see the tls_qualys.py scanner.

"""
import logging
from datetime import datetime, timedelta

import pytz
from celery import Task, group

from websecmap.organizations.models import Url
from websecmap.scanners.scanner.__init__ import allowed_to_scan, chunks2, q_configurations_to_scan
from websecmap.scanners.scanner.tls_qualys import claim_proxy, qualys_scan_bulk, release_proxy
import random

log = logging.getLogger(__name__)


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
    **kwargs
) -> Task:

    if not kwargs.get('exclude_urls_scanned_in_the_last_n_days', 0):
        raise ValueError('exclude_urls_scanned_in_the_last_n_days was not found in tls qualys periodic task kwargs.')

    if not urls_filter.get('endpoint__endpointgenericscan__rating__in', 0):
        raise ValueError('endpoint__endpointgenericscan__rating__in was not found in urls_filter.')

    if not allowed_to_scan("tls_qualys"):
        return group()

    # use order by to get a few of the most outdated results...
    urls = Url.objects.filter(
        q_configurations_to_scan(),
        is_dead=False,
        not_resolvable=False,
        endpoint__protocol="https",
        endpoint__port=443,
        endpoint__is_dead=False,
        endpoint__endpointgenericscan__is_the_latest_scan=True,

        # an exclude filter here will not work, as you will exclude so much...
        endpoint__endpointgenericscan__last_scan_moment__lte=datetime.now(tz=pytz.utc) - timedelta(
            days=kwargs.get('exclude_urls_scanned_in_the_last_n_days', 3)),
        **urls_filter
    ).order_by(
        '-endpoint__endpointgenericscan__latest_scan_moment'
    ).only('id', 'url')

    # Due to filtering on endpoints, the list of URLS is not distinct. We're making it so.
    urls = list(set(urls))
    random.shuffle(urls)

    if not urls:
        log.warning('Applied filters resulted in no urls, thus no tls qualys tasks!')
        return group()

    chunks = list(chunks2(urls, 25))

    tasks = []
    for chunk in chunks:
        tasks.append(claim_proxy.s(chunk[0]) | qualys_scan_bulk.s(chunk) | release_proxy.s(chunk[0]))
    return group(tasks)
