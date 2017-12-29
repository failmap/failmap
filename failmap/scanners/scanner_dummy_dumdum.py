"""Exemplary and experimentation scanner.

This scanner serves as an example/template for other scanners and as a early adopter of
new methods/processes in scanner development.
"""

import logging
import random
import time
from typing import List

from celery import Task, group

from failmap.celery import ParentFailed, app
from failmap.organizations.models import Organization, Url
from failmap.scanners.endpoint_scan_manager import EndpointScanManager

from .common import organizations_from_names
from .models import Endpoint

log = logging.getLogger(__name__)

# how often a task should be retried when encountering an expectable exception
MAX_RETRIES = 3
RETRY_DELAY = 1
# after which time a pending task should no longer be accepted by a worker
EXPIRES = 5


@app.task
def scan(
    organizations: dict = None,
    urls: dict = None,
    endpoints: dict = None
) -> Task:
    """Compose and execute taskset to scan specified organizations.

    :param organizations: dict: limit organizations to scan to these filters, see below
    :param urls: dict: limit urls to scan to these filters, see below
    :param endpoints: dict: limit endpoints to scan to these filters, see below

    Depending on the type of scanner (endpoint, domain level, etc) a list of scanable
    items will be generated and a taskset will be composed to allow scanning of these items.

    By default all elegible items will be used. Which means a complete scan of everything possible
    with this scanner.

    By specifying filters the list of items to scan can be reduced. These filters are passed to
    Django QuerySet filters on the respective models.

    For example, to scan all urls/endpoints for one organization named 'example' run:

    >>> scan(organizations={'name__iexact': 'example})

    Multiple filters can be applied, to scan only port 80 for organizations added today run:

    >>> scan(
    ...     organizations={'date_added__day': datetime.datetime.today().day},
    ...     endpoints={'port': 80}
    ... )

    """
    task = compose(organizations_from_names(organizations))

    return task


def compose(organizations: List[Organization]):
    """Compose taskset to scan specified organizations.

    :param organizations: List[Organization]:
    :param organizations: List[Organization]:

    """

    # collect all scannable urls for provided organizations
    urls = Url.objects.all().filter(is_dead=False,
                                    not_resolvable=False,
                                    organization__in=organizations)

    endpoints = Endpoint.objects.all().filter(url__in=urls, is_dead=False, protocol__in=['http', 'https'])

    log.debug('scanning %s endpoints for %s urls for %s organizations',
              len(endpoints), len(urls), len(organizations))

    def compose_subtasks(endpoint):
        """Create a task chain of scan & store for a given endpoint.

        :param endpoint:

        """
        scan_task = scan_dummy.s(endpoint.uri_url())
        store_task = store_dummy.s(endpoint)
        return scan_task | store_task

    # create a group of parallel executable scan&store tasks for all endpoints
    taskset = group(compose_subtasks(endpoint) for endpoint in endpoints)

    return taskset


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
