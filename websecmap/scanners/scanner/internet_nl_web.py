"""
See internet NL Mail scanner documentation. This uses the same code.

Special note: you may receive other fields in their answer. The fields you receive are based on a certain view of
 the data they store.
"""

import logging

from celery import Task, group
from constance import config

from websecmap.organizations.models import Url
from websecmap.scanners.scanner.__init__ import (allowed_to_scan, q_configurations_to_scan,
                                                 url_filters)
from websecmap.scanners.scanner.internet_nl_mail import register_scan

log = logging.getLogger(__name__)


API_URL_WEB = "https://batch.internet.nl/api/batch/v1.0/web/"
MAX_INTERNET_NL_SCANS = 5000


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
    **kwargs
) -> Task:

    if not allowed_to_scan("internet_nl_web"):
        return group()

    # todo: has to have HTTP/HTTPS endpoints.
    default_filter = {"is_dead": False, "not_resolvable": False}
    urls_filter = {**urls_filter, **default_filter}
    endpoints_filter = {'protocol__in': ['dns_a_aaa']}
    urls = Url.objects.all().filter(q_configurations_to_scan(level='url'), **urls_filter)
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter)

    if not urls:
        log.warning('Applied filters resulted in no urls, thus no mail scan tasks!')
        return group()

    urls = list(set(urls))

    # do all in one. Throw exception at more than 5000.
    if len(urls) >= MAX_INTERNET_NL_SCANS:
        raise ValueError("Attempting to scan more than 5000 urls on internet.nl, which is above the daily limit. "
                         "Slice your scan requests to be at maximum 5000 urls per day.")

    log.info('Creating internet_nl_web scan task for %s urls.', len(urls))

    return group([register_scan.si(urls, config.INTERNET_NL_API_USERNAME, config.INTERNET_NL_API_PASSWORD,
                                   'web', API_URL_WEB)])
