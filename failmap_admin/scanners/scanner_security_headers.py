"""
Check if the https site uses HSTS to tell the browser the site should only be reached over HTTPS.
(useful until browsers do https by default, instead of by choice)
"""
import logging
import subprocess
from datetime import datetime

import pytz
import untangle
from django.core.exceptions import ObjectDoesNotExist

from failmap_admin.organizations.models import Url
from failmap_admin.scanners.endpoint_scan_manager import EndpointScanManager
from failmap_admin.scanners.models import EndpointGenericScanScratchpad
from failmap_admin.scanners.scanner_http import ScannerHttp

from .models import Endpoint

logger = logging.getLogger(__package__)


class ScannerSecurityHeaders:

    @staticmethod
    def scan_all_urls():
        """
        :return:
        """
        urls = Url.objects.all().filter(is_dead=False,
                                        not_resolvable=False)

        for url in urls:
            ScannerSecurityHeaders.scan_headers(url)

    @staticmethod
    def scan_organization(organization):
        urls = Url.objects.all().filter(is_dead=False,
                                        not_resolvable=False,
                                        organization=organization)
        for url in urls:
            ScannerSecurityHeaders.scan_headers(url)

    @staticmethod
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
            if endpoint.is_ipv4():
                eps.append(endpoint)

        for endpoint in eps:
            headers = ScannerSecurityHeaders.get_headers(endpoint)

            if headers:
                egss = EndpointGenericScanScratchpad()
                egss.when = datetime.now(pytz.utc)
                egss.data = headers
                egss.type = "security headers"
                egss.domain = endpoint.uri_url()
                egss.save()

                ScannerSecurityHeaders.analyze_headers(endpoint, headers)
            else:
                logger.debug('No headers found, probably an error.')

    @staticmethod
    def analyze_headers(endpoint, headers):

        ScannerSecurityHeaders.generic_check(endpoint, headers, 'X-XSS-Protection')
        ScannerSecurityHeaders.generic_check(endpoint, headers, 'X-Frame-Options')
        ScannerSecurityHeaders.generic_check(endpoint, headers, 'X-Content-Type-Options')

        if endpoint.protocol == "https":
            ScannerSecurityHeaders.generic_check(endpoint, headers, 'Strict-Transport-Security')


    @staticmethod
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

    @staticmethod
    def get_headers(endpoint):
        from requests import ReadTimeout, ConnectTimeout, HTTPError, Timeout, ConnectionError
        import requests
        try:
            # ignore wrong certificates, those are handled in a different scan.
            # Only get the first website, that should be fine (todo: also any redirects)
            response = requests.get(endpoint.uri_url(), timeout=(10, 10), allow_redirects=False,
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
            # requests.exceptions.ChunkedEncodingError: ('Connection broken: IncompleteRead(0 bytes read)', IncompleteRead(0 bytes read))
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

