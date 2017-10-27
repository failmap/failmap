"""
Check if the https site uses HSTS to tell the browser the site should only be reached over HTTPS.
(useful until browsers do https by default, instead of by choice)
"""
import logging
from datetime import datetime

import pytz
from celery import Celery
from celery.task import task

from failmap_admin.celery import app
from failmap_admin.organizations.models import Url
from failmap_admin.scanners.endpoint_scan_manager import EndpointScanManager
from failmap_admin.scanners.models import EndpointGenericScanScratchpad

from .models import Endpoint

logger = logging.getLogger(__package__)


def scan_all_urls():
    """
    hangs often for a few seconds
    300 urls takes 178 seconds
    :return:
    """
    urls = Url.objects.all().filter(is_dead=False,
                                    not_resolvable=False)

    for url in urls:
        scan_headers(url)


def scan_all_urls_celery():
    """
    300 urls takes 60 seconds. Is 3x as fast, and it scales over multiple queues / servers.
    Has four workers.
    :return:
    """
    urls = Url.objects.all().filter(is_dead=False,
                                    not_resolvable=False)[0:10]

    for url in urls:
        scan_header_celery(url)


def scan_organization(organization):
    urls = Url.objects.all().filter(is_dead=False,
                                    not_resolvable=False,
                                    organization=organization)
    for url in urls:
        scan_headers(url)


def scan_organization_celery(organization):
    urls = Url.objects.all().filter(is_dead=False,
                                    not_resolvable=False,
                                    organization=organization)
    for url in urls:
        scan_header_celery(url)


def scan_headers(url):
    # get website headers using request library
    # don't redirect, otherwise count scores for _all_ redirections (which can be a lot :))

    # Only stores a Yes or No per header? And in the message the value. Can be multiple with
    # redirects? - Store headers?
    # each header can change over time.
    # so we can store it as a generic scan.
    # depending on dns settings we can do both ipv6 and ipv4.
    # currently only doing ipv4. Until we have an ipv6 network (rabitmq)
    # we should be able to determine if we are on an ipv6 or ipv4 machine, perhaps in os.environ
    eps = []
    http_endpoints = Endpoint.objects.all().filter(url=url, is_dead=False, protocol='http')
    https_endpoints = Endpoint.objects.all().filter(url=url, is_dead=False, protocol='https')
    endpoints = list(http_endpoints) + list(https_endpoints)
    for endpoint in endpoints:
        if not endpoint.is_ipv6():
            eps.append(endpoint)

    for endpoint in eps:
        headers = get_headers(endpoint.uri_url())

        if headers:
            egss = EndpointGenericScanScratchpad()
            egss.when = datetime.now(pytz.utc)
            egss.data = headers
            egss.type = "security headers"
            egss.domain = endpoint.uri_url()
            egss.save()

            analyze_headers(headers, endpoint)
        else:
            logger.debug('No headers found, probably an error.')


def scan_header_celery(url):
    # from .tasks import dispatch_scan_security_headers
    # get website headers using request library
    # don't redirect, otherwise count scores for _all_ redirections (which can be a lot :))

    # Only stores a Yes or No per header? And in the message the value. Can be multiple with
    # redirects? - Store headers?
    # each header can change over time.
    # so we can store it as a generic scan.
    # depending on dns settings we can do both ipv6 and ipv4.
    # currently only doing ipv4. Until we have an ipv6 network (rabitmq)
    # we should be able to determine if we are on an ipv6 or ipv4 machine, perhaps in os.environ
    eps = []
    http_endpoints = Endpoint.objects.all().filter(url=url, is_dead=False, protocol='http')
    https_endpoints = Endpoint.objects.all().filter(url=url, is_dead=False, protocol='https')
    # todo: don't scan per endpoint, but scan per URL. Multiple endp[oints with everything the
    # same except IP doesn't really add anything as the ratings will be the same every time.

    endpoints = list(http_endpoints) + list(https_endpoints)
    for endpoint in endpoints:
        if not endpoint.is_ipv6():
            dispatch_scan_security_headers(endpoint, 'IPv4')
        # ipv6 not supported yet.
        # else:
            # dispatch_scan_security_headers(endpoint, 'IPv6')


def dispatch_scan_security_headers(endpoint, queue):
    # from .tasks import get_headers_celery
    url = endpoint.uri_url()
    scan_task = get_headers.s(url)
    store_task = analyze_headers.s(endpoint)

    # the order of arguments for the store task is relevant. First the result then whatever you want
    task = (scan_task | store_task)

    # can be either IPv4 or IPv6. Not all may be available.
    # First check if the route exists. (slow?)

    task.apply_async()


@app.task
def analyze_headers(headers, endpoint):
    if not headers:
        return

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


@app.task
def get_headers(uri_url):
    from requests import ReadTimeout, ConnectTimeout, HTTPError, Timeout, ConnectionError
    import requests
    try:
        # ignore wrong certificates, those are handled in a different scan.
        # Only get the first website, that should be fine (todo: also any redirects)
        response = requests.get(uri_url, timeout=(10, 10), allow_redirects=False,
                                verify=False)
        for header in response.headers:
            logger.debug('Received header: %s' % header)
        return response.headers
    except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError, Exception):
        # No decent way to deal with ChunkedEncodingError. So then just do a broad exception.
        # can't really show a meaningful error. There are a lot of possibilities.
        # requests.exceptions.ChunkedEncodingError
        # the exceptions throw even more exceptions,
        # like requests.exceptions.ChunkedEncodingError
        # requests.exceptions.ChunkedEncodingError: ('Connection broken: IncompleteRead(0 bytes read)', \
        #        IncompleteRead(0 bytes read))
        # if ConnectTimeout:
        #     logger.error("Connection timeout %s" % ConnectTimeout.strerror)
        # if HTTPError:
        #     logger.error("HTTPError %s" % HTTPError.strerror)
        # if ReadTimeout:
        #     logger.error("ReadTimeout %s" % ReadTimeout.strerror)
        # if Timeout:
        #     logger.error("Timeout %s" % Timeout.strerror)
        # if ConnectionError:
        #     logger.error("ConnectionError %s" % ConnectionError.strerror)

        logger.error("Request resulted into an error.")
        return
