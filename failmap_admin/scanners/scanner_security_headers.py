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

    if not endpoints:
        raise Endpoint.DoesNotExist("No endpoints exist for the selected urls.")

    logger.debug('scanning %s endpoints for %s urls', len(endpoints), len(urls))

    def compose_subtasks(endpoint):
        """Create a task chain of scan & store for a given endpoint."""
        scan_task = get_headers.s(endpoint.uri_url())
        store_task = analyze_headers.s(endpoint)
        return scan_task | store_task

    # create a group of parallel executable scan&store tasks for all endpoints
    taskset = group(compose_subtasks(endpoint) for endpoint in endpoints)

    return taskset


@app.task
def analyze_headers(result: requests.Response, endpoint):
    # if scan task failed, ignore the result (exception) and report failed status
    if isinstance(result, Exception):
        return ParentFailed('skipping result parsing because scan failed.', cause=result)

    response = result

    # scratch it, for debugging.
    egss = EndpointGenericScanScratchpad()
    egss.when = datetime.now(pytz.utc)
    egss.data = "Status: %s, Headers: %s, Redirects: %s" % (response.status_code, response.headers, response.history)
    egss.type = "security headers"
    egss.domain = endpoint.uri_url()
    egss.save()

    generic_check(endpoint, response.headers, 'X-XSS-Protection')
    generic_check(endpoint, response.headers, 'X-Frame-Options')
    generic_check(endpoint, response.headers, 'X-Content-Type-Options')

    """
    https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security
    Note: The Strict-Transport-Security header is ignored by the browser when your site is accessed using HTTP; 
    this is because an attacker may intercept HTTP connections and inject the header or remove it.  When your 
    site is accessed over HTTPS with no certificate errors, the browser knows your site is HTTPS capable and will 
    honor the Strict-Transport-Security header.
    """
    if endpoint.protocol == "https":
        generic_check(endpoint, response.headers, 'Strict-Transport-Security')

    return {'status': 'success'}


def generic_check(endpoint: Endpoint, headers, header):
    # this is case insensitive
    if header in headers.keys():
        logger.debug('Has %s' % header)
        EndpointScanManager.add_scan(header,
                                     endpoint,
                                     'True',
                                     headers[header])
    else:
        logger.debug('Has no %s' % header)
        EndpointScanManager.add_scan(header,
                                     endpoint,
                                     'False',
                                     "Security Header not present: %s" % header)


def error_response_400_500(endpoint):
    # Set all headers for this endpoint to 400_500, which are not shown in the report.
    # These are not shown in the report anymore. Not using this
    EndpointScanManager.add_scan('X-XSS-Protection', endpoint, '400_500', "")
    EndpointScanManager.add_scan('X-Frame-Options', endpoint, '400_500', "")
    EndpointScanManager.add_scan('X-Content-Type-Options', endpoint, '400_500', "")

    if endpoint.protocol == "https":
        EndpointScanManager.add_scan('Strict-Transport-Security', endpoint, '400_500', "")


@app.task(bind=True, default_retry_delay=1, retry_kwargs={'max_retries': 3})
def get_headers(self, uri_url):
    """
        Issue #94:
        TL;DR: The fix is to follow all redirects.

        Citing: https://stackoverflow.com/questions/22077618/respect-x-frame-options-with-http-redirect
        Source: https://tools.ietf.org/html/rfc7034
        Thanks to: antoinet.

        From the terminology used in RFC 7034,

        The use of "X-Frame-Options" allows a web page from host B to declare that its content (for example, a
        button, links, text, etc.) must not be displayed in a frame (<frame> or <iframe>) of another page (e.g.,
        from host A). This is done by a policy declared in the HTTP header and enforced by browser implementations
        as documented here.

        The X-Frame-Options HTTP header field indicates a policy that specifies whether the browser should render
        the transmitted resource within a <frame> or an <iframe>. Servers can declare this policy in the header of
        their HTTP responses to prevent clickjacking attacks, which ensures that their content is not embedded
        into other pages or frames.


        Similarly, since a redirect is a flag not to render the content, the content can't be manipulated.
        This also means no X-XSS-Protection or X-Content-Type-Options are needed. So just follow all redirects.

        :return: requests.response
        """

    try:
        # ignore wrong certificates, those are handled in a different scan.
        # 10 seconds for network delay, 10 seconds for the site to respond.
        response = requests.get(uri_url, timeout=(10, 10), allow_redirects=True, verify=False)

        # Removed: only continue for valid responses (eg: 200)
        # Error pages, such as 404 are super fancy, with forms and all kinds of content.
        # it's obvious that such pages (with content) follow the same security rules as any 2XX response.
        # if 400 <= response.status_code <= 600:
        #     error_response_400_500(endpoint)
        # response.raise_for_status()

        for header in response.headers:
            logger.debug('Received header: %s' % header)
        return response
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
