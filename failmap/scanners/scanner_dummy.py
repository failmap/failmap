"""Exemplary and experimentation scanner.

This scanner serves as an example/template for other scanners and as a early adopter of
new methods/processes in scanner development.
"""

import logging
import random
import time

from celery import Task, group

from failmap.celery import ParentFailed, app
from failmap.organizations.models import Organization, Url
from failmap.scanners.endpoint_scan_manager import EndpointScanManager

from .models import Endpoint

log = logging.getLogger(__name__)

# how often a task should be retried when encountering an expectable exception
MAX_RETRIES = 3
RETRY_DELAY = 1
# after which time a pending task should no longer be accepted by a worker
EXPIRES = 5


def create_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    """Compose taskset to scan specified endpoints.

    :param organizations_filter: dict: limit organizations to scan to these filters, see below
    :param urls_filter: dict: limit urls to scan to these filters, see below
    :param endpoints_filter: dict: limit endpoints to scan to these filters, see below

    Depending on the type of scanner (endpoint, domain level, etc) a list of scanable
    items will be generated and a taskset will be composed to allow scanning of these items.

    By default all elegible items will be scanned. Which means a complete scan of everything possible
    with this scanner.

    By specifying filters the list of items to scan can be reduced. These filters are passed to
    Django QuerySet filters on the respective models.

    For example, to scan all urls/endpoints for one organization named 'example' run:

    >>> task = create_task(organizations={'name__iexact': 'example'})
    >>> result = task.apply_async()
    >>> print(result.get())

    (`name__iexact` matches the name case-insensitive)

    Multiple filters can be applied, to scan only port 80 for organizations added today run:

    >>> task = create_task(
    ...     organizations={'date_added__day': datetime.datetime.today().day},
    ...     endpoints={'port': 80}
    ... )

    """

    # The dummy scanner is an example of a scanner that scans on an endpoint
    # level. Meaning to create tasks for scanning, this function needs to be
    # smart enough to translate (filtered) lists of organzations and urls into a
    # (filtered) lists of endpoints (or use a url filter directly). This list of
    # endpoints is then used to create a group of tasks which would perform the
    # scan.

    # apply filter to organizations (or if no filter, all organizations)
    organizations = Organization.objects.filter(**organizations_filter)
    # apply filter to urls in organizations (or if no filter, all urls)
    urls = Url.objects.filter(organization__in=organizations, **urls_filter)

    # select endpoints to scan based on filters
    endpoints = Endpoint.objects.filter(
        # apply filter to endpoints (or if no filter, all endpoints)
        url__in=urls, **endpoints_filter,
        # also apply manditory filters to only select valid endpoints for this action
        is_dead=False, protocol__in=['http', 'https'])

    log.info('Creating scan task for %s endpoints for %s urls for %s organizations.',
             len(endpoints), len(urls), len(organizations))

    # create tasks for scanning all selected endpoints as a single managable group
    task = group(
        scan_dummy.s(endpoint.uri_url()) | store_dummy.s(endpoint) for endpoint in endpoints
    )

    return task


@app.task
def store_dummy(result, endpoint):
    """

    :param result: param endpoint:
    :param endpoint:

    """
    # if scan task failed, ignore the result (exception) and report failed status
    if isinstance(result, Exception):
        return ParentFailed('skipping result parsing because scan failed.', cause=result)

    log.debug('Storing result: %s, for endpoint: %s.', result, endpoint)
    if result:
        EndpointScanManager.add_scan(
            'Dummy', endpoint, 'True', 'Because the result was True')
    else:
        EndpointScanManager.add_scan(
            'Dummy', endpoint, 'False', 'Because the result was False')

    # return something informative
    return {'status': 'success', 'result': result}


class SomeError(Exception):
    """Just some expectable error."""


@app.task(bind=True,
          default_retry_delay=RETRY_DELAY,
          retry_kwargs={'max_retries': MAX_RETRIES},
          expires=EXPIRES)
def scan_dummy(self, uri_url):
    """

    :param uri_url:

    """
    try:
        log.info('Start scanning %s', uri_url)

        # sometimes a task fails
        if not random.randint(0, 5):
            raise SomeError('some error occured')

        # often tasks take different times to execute
        time.sleep(random.randint(1, 10) / 10)

        # the result can be different
        result = bool(random.randint(0, 1))

        log.info('Done scanning: %s, result: %s', uri_url, result)
        return result
    except SomeError as e:
        # If an expected error is encountered put this task back on the queue to be retried.
        # This will keep the chained logic in place (saving result after successful scan).
        # Retry delay and total number of attempts is configured in the task decorator.
        try:
            # Since this action raises an exception itself, any code after this won't be executed.
            raise self.retry(exc=e)
        except BaseException:
            # If this task still fails after maximum retries the last
            # error will be passed as result to the next task.
            log.exception('Retried %s times and it still failed', MAX_RETRIES)
            return e
