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
from django.conf import settings

from .models import Endpoint

log = logging.getLogger(__name__)

# how often a task should be retried when encountering an expectable exception
MAX_RETRIES = 3
RETRY_DELAY = 1
# after which time a pending task should no longer be accepted by a worker
EXPIRES = 5


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    """Compose taskset to scan specified endpoints.

    *This is an implementation of `compose_task`. For more documentation about this concept, arguments and concrete
    examples of usage refer to `compose_task` in `types.py`.*

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

    if not endpoints:
        raise Exception('Applied filters resulted in no tasks!')

    log.info('Creating scan task for %s endpoints for %s urls for %s organizations.',
             len(endpoints), len(urls), len(organizations))

    # make sure we're dealing with a list for the coming random function
    endpoints = list(endpoints)
    # randomize the endpoints so hosts are contacted in random order (less pressure)
    random.shuffle(endpoints)

    # create tasks for scanning all selected endpoints as a single managable group
    # Sending entire objects is possible. How signatures (.s and .si) work is documented:
    # http://docs.celeryproject.org/en/latest/reference/celery.html#celery.signature
    task = group(
        scan_dummy.s(endpoint.uri_url()) | store_dummy.s(endpoint) for endpoint in endpoints
    )

    return task


@app.task(queue='storage')
def store_dummy(result, endpoint):
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
        EndpointScanManager.add_scan('Dummy', endpoint, 'True', message_result_ok)
    else:
        EndpointScanManager.add_scan('Dummy', endpoint, 'False', message_result_false)

    # return something informative
    return {'status': 'success', 'result': result}


class SomeError(Exception):
    """Just some expectable error."""


@app.task(queue='scanners',
          bind=True,
          default_retry_delay=RETRY_DELAY,
          retry_kwargs={'max_retries': MAX_RETRIES},
          expires=EXPIRES)
def scan_dummy(self, uri_url):
    """

    Before committing your scanner, verify the following:
    [ ] the scanner does not keep connections open (resource claim on both our and their servers)
    [ ] a series of exceptions are handled: keep in mind the high probability of network errors
    [ ] does not try to authenticate _ever_ (== filling in usernames / passwords)
    [ ] does only one thing very well

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
        #        'output_dir': OUTPUT_DIR + os.environ.get('YOURTOOL_OUTPUT_DIR', "scanners/resources/output/yourtool/"),
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
