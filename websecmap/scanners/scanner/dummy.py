"""Exemplary and experimentation scanner.

This scanner serves as an example/template for other scanners and as a early adopter of
new methods/processes in scanner development.
"""

import logging
import random
import time

from celery import Task, group
from django.conf import settings

from websecmap.celery import ParentFailed, app
from websecmap.scanners.models import Endpoint
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.scanner import (allowed_to_scan, endpoint_filters,
                                                q_configurations_to_scan)

log = logging.getLogger(__name__)

# how often a task should be retried when encountering an expectable exception
MAX_RETRIES = 3

# time in seconds how long it should take before a retry is attempted
RETRY_DELAY = 1

# time in seconds, after which time a pending task should no longer be accepted by a worker
EXPIRES = 3600 * 10  # 10 hour example


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
    **kwargs
) -> Task:
    """Compose taskset to scan specified endpoints.

    *This is an implementation of `compose_task`.
    For more documentation about this concept, arguments and concrete
    examples of usage refer to `compose_task` in `types.py`.*
    """

    if not allowed_to_scan("dummy"):
        log.warning("Dummy scanner is not allowed to scan.")
        return group()

    endpoints = Endpoint.objects.filter(
        q_configurations_to_scan(level='endpoint'),
        # only scan endpoints that are known to be alive, using the http(s) protocol
        is_dead=False, protocol__in=['http', 'https'])

    endpoints = endpoint_filters(endpoints, organizations_filter, urls_filter, endpoints_filter)

    if not endpoints:
        log.warning('Applied filters resulted in no endpoints, thus no dummy tasks!')
        return group()

    log.info('Creating dummy scan task for %s endpoints ', len(endpoints))

    """
    Make sure there are no duplicate endpoints in the set: some filters may have resulted in a cartesian product.
    Randomize the list of endpoints, so that scanned hosts experience less pressure / less requests per second.
    """
    endpoints = list(set(endpoints))
    random.shuffle(endpoints)

    # Make the first task immutable, so it doesn't get any arguments of other scanners in a chain.
    # http://docs.celeryproject.org/en/latest/reference/celery.html#celery.signature
    task = group(
        scan.si(endpoint.uri_url()) | store.s(endpoint) for endpoint in endpoints
    )

    return task


@app.task(queue='storage')
def store(result, endpoint):
    """

    :param result: param endpoint:
    :param endpoint:

    """
    # if scan task failed, ignore the result (exception) and report failed status
    if isinstance(result, Exception):
        return ParentFailed('skipping result parsing because scan failed.', cause=result)

    # Messages are translated for display. Add the exact messages in: /failmap/map/static/js/script.js
    # Run "failmap translate" to have the messages added to:
    # /failmap/map/locale/*/djangojs.po
    # /failmap/map/locale/*/django.po
    # translate them and then run "failmap translate" again.
    message_result_ok = 'Because the result was True'
    message_result_false = 'Because the result was False'

    log.debug('Storing result: %s, for endpoint: %s.', result, endpoint)
    # You can save any (string) value and any (string) message.
    # The EndpointScanManager deduplicates the data for you automatically.
    if result:
        store_endpoint_scan_result('Dummy', endpoint, 'True', message_result_ok)
    else:
        store_endpoint_scan_result('Dummy', endpoint, 'False', message_result_false)

    # return something informative
    return {'status': 'success', 'result': result}


class SomeError(Exception):
    """Just some expectable error."""


# The isolated queue means no network connection.
@app.task(queue='storage',
          bind=True,
          default_retry_delay=RETRY_DELAY,
          retry_kwargs={'max_retries': MAX_RETRIES},
          expires=EXPIRES)
def scan(self, uri_url):
    """

    Before committing your scanner, verify the following:
    [ ] the scanner does not keep connections open. Doing otherwise claims resources on our and their
        machines. This can lead to resource depletion and possible denial of service.
    [ ] network connection errors are common, especially if you don't know if a service really exists. Be aware
        that there are many types of network errors: you can see examples in our other scanners.
    [ ] authentication on a service when you're not allowed to is seen as a crime in many places, therefore
        a scanner cannot do any form of authentication (even admin/admin).
    [ ] try to do only one thing pretty well: you'll find that there is so much stuff involved just to do one thing
        very well... even the most simplest of tasks will fail and give exceptions in the most unexpected and
        spectacular ways.

    :param uri_url:

    """
    try:
        log.info('Start scanning %s', uri_url)

        # Tools and output for this scan are registered in /failmap/settings.py
        # We prefer tools written in python, limiting the amount of dependencies used in the project.
        # Another tool is fine too, but please announce so in chat etc.
        # Example:
        # TOOLS = {
        #    'yourtool': {
        #        'executable': VENDOR_DIR + os.environ.get('YOURTOOL_EXECUTABLE', "yourtool/yourtool.py"),
        #        'output_dir': OUTPUT_DIR + os.environ.get('YOURTOOL_OUTPUT_DIR',
        #                                                  "scanners/resources/output/yourtool/"),
        #    },
        # mytool = settings.TOOLS['youtool']['executable']
        # Below demonstrates the usage of settings.
        sample_settings_usage = len(settings.TOOLS)
        log.debug("%s are registered." % sample_settings_usage)

        # simulation: sometimes a task fails, for example with network errors etcetera. The task will be retried.
        if not random.randint(0, 5):
            raise SomeError('some error occured')

        # simulation: often tasks take different times to execute
        time.sleep(random.randint(1, 10) / 10)

        # simulation: the result can be different
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
