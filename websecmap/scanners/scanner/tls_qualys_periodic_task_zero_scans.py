"""
This is a version of the TLS scanner that only scans endpoints that did not have a scan yet.
For more documentation, see the other periodic task
"""

import logging

from celery import Task, group
from django.db.models import Count

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

    if not allowed_to_scan("tls_qualys"):
        return group()

    # only get new endpoints that do not have any tls scan as of yet...
    # once scanned, they will be re-scanned depending if there is a higher risk.
    # This approach reduces the amount of scans needed significantly.
    urls = Url.objects.filter(
        q_configurations_to_scan(),
        is_dead=False,
        not_resolvable=False,
        endpoint__protocol="https",
        endpoint__port=443,
        endpoint__is_dead=False,
        **urls_filter
    ).annotate(
        nr_of_scans=Count('endpoint__endpointgenericscan')
    ).filter(
        nr_of_scans=0
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
