"""
Check if the https site uses HSTS to tell the browser the site should only be reached over HTTPS.
(useful until browsers do https by default, instead of by choice)
"""
import logging
from datetime import datetime
from typing import List

import pytz
import requests
from celery import group
from requests import ConnectionError, ConnectTimeout, HTTPError, ReadTimeout, Timeout

from failmap_admin.celery import ParentFailed, app
from failmap_admin.organizations.models import Organization, Url
from failmap_admin.scanners.endpoint_scan_manager import EndpointScanManager
from failmap_admin.scanners.models import EndpointGenericScanScratchpad

from .models import Endpoint

logger = logging.getLogger(__name__)


def organizations_from_names(organization_names: List[str]) -> List[Organization]:
    """Turn list of organization names into list of Organization objects.

    Will return all organizations if none are specified.
    """
    # select specified or all organizations to be scanned
    if organization_names:
        organizations = list()
        for organization_name in organization_names:
            try:
                organizations.append(Organization.objects.get(name__iexact=organization_name))
            except Organization.DoesNotExist as e:
                raise Exception("Failed to find organization '%s' by name" % organization_name) from e
    else:
        organizations = Organization.objects.all()

    return organizations


@app.task
def scan(organization_names: List[str], execute=True):
    """Compose and execute taskset to scan specified organizations."""
    task = compose(organizations=organizations_from_names(organization_names))
    if execute:
        return task.apply_async()
    else:
        return task


@app.task
def scan_urls(urls: List[Url], execute=True):
    """Compose and execute taskset to scan specified urls."""
    task = compose(urls=urls)
    return task.apply_async() if execute else task


def compose(organizations: List[Organization]=None, urls: List[Url]=None):
    """Compose taskset to scan specified organizations or urls (not both)."""

    if not any([organizations, urls]):
        raise ValueError("No organizations or urls supplied.")

    # collect all scannable urls for provided organizations
    if organizations:
        urls_organizations = Url.objects.all().filter(is_dead=False,
                                                      not_resolvable=False,
                                                      organization__in=organizations)

        urls = list(urls_organizations) + urls if urls else list(urls_organizations)

    endpoints = Endpoint.objects.all().filter(url__in=urls, is_dead=False, protocol__in=['http', 'https'])

    logger.debug('scanning %s endpoints for %s urls for %s organizations',
                 len(endpoints), len(urls), len(organizations))

    def compose_subtasks(endpoint):
        """Create a task chain of scan & store for a given endpoint."""
        scan_task = get_headers.s(endpoint.uri_url())
        store_task = analyze_headers.s(endpoint)
        return scan_task | store_task

    # create a group of parallel executable scan&store tasks for all endpoints
    taskset = group(compose_subtasks(endpoint) for endpoint in endpoints)

    return taskset


@app.task
def analyze_headers(result, endpoint):
    # if scan task failed, ignore the result (exception) and report failed status
    if isinstance(result, Exception):
        return ParentFailed('skipping result parsing because scan failed.', cause=result)

    headers = result

    # scratch it, for debugging.
    egss = EndpointGenericScanScratchpad()
    egss.when = datetime.now(pytz.utc)
    egss.data = headers
    egss.type = "security headers"
    egss.domain = endpoint.uri_url()
    egss.save()

    generic_check(endpoint, headers, 'X-XSS-Protection')
    generic_check(endpoint, headers, 'X-Frame-Options')
    generic_check(endpoint, headers, 'X-Content-Type-Options')

    if endpoint.protocol == "https":
        generic_check(endpoint, headers, 'Strict-Transport-Security')

    return {'status': 'success'}


def generic_check(endpoint, headers, header):
    if header in headers.keys():  # this is case insensitive
        logger.debug('Has %s' % header)
        EndpointScanManager.add_scan(header,
                                     endpoint,
                                     'True',
                                     headers[header])  # exploitable :)
    else:
        logger.debug('Has no %s' % header)
        EndpointScanManager.add_scan(header,
                                     endpoint,
                                     'False',
                                     "Security Header not present: %s" % header)


@app.task(bind=True, default_retry_delay=1, retry_kwargs={'max_retries': 3})
def get_headers(self, uri_url):
    try:
        # ignore wrong certificates, those are handled in a different scan.
        # Only get the first website, that should be fine (todo: also any redirects)
        response = requests.get(uri_url, timeout=(10, 10), allow_redirects=False,
                                verify=False)
        # only continue for valid responses (eg: 200)
        response.raise_for_status()

        for header in response.headers:
            logger.debug('Received header: %s' % header)
        return response.headers
    except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError) as e:
        # If an expected error is encountered put this task back on the queue to be retried.
        # This will keep the chained logic in place (saving result after successful scan).
        # Retry delay and total number of attempts is configured in the task decorator.
        try:
            # Since this action raises an exception itself, any code after this won't be executed.
            raise self.retry(exc=e)
        except BaseException:
            # If this task still fails after maximum retries the last
            # error will be passed as result to the next task.
            return e
