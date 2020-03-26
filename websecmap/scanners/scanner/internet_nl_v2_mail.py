"""
Implementation of Internet.nl API v2.0

Docs: https://api.internet.nl/v2/documentation/

Internet.nl scans for modern web and mail standards. Such as https, SPF, DNSSEC, STARTTLS et cetera.
"""

import logging

from celery import Task, group

from websecmap.organizations.models import Url
from websecmap.scanners.scanner.__init__ import (allowed_to_scan, q_configurations_to_scan,
                                                 url_filters)
from websecmap.scanners.scanner.internet_nl_v2_websecmap import initialize_scan

log = logging.getLogger(__name__)


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
    **kwargs
) -> Task:

    if not allowed_to_scan("internet_nl_mail"):
        return group()

    default_filter = {"is_dead": False, "not_resolvable": False}
    urls_filter = {**urls_filter, **default_filter}
    urls = Url.objects.all().filter(q_configurations_to_scan(level='url'), **urls_filter)

    endpoints_filter = {'is_dead': False, "protocol": 'dns_mx_no_cname'}
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter)
    urls = urls.only("url")
    urls = urls.value_list("url", flat=True)

    if not urls:
        log.warning('Applied filters resulted in no urls, thus no mail scan tasks!')
        return group()

    urls = list(set(urls))

    log.info('Creating internetnl mail scan task for %s urls.', len(urls))

    return group([initialize_scan.si("mail", urls)])
