"""
Check if a domain is only reachable on plain http, instead of both http and https

Browsers first connect to http, not https when entering a domain. That will be changed in the
future.

"""
import logging
import subprocess
from datetime import datetime

import pytz
import untangle
from django.core.exceptions import ObjectDoesNotExist

from failmap_admin.organizations.models import Organization, Url
from failmap_admin.scanners.scanner_http import ScannerHttp

from .models import Endpoint

logger = logging.getLogger(__package__)


class ScannerPlainHttp:

    def scan(self):
        """
        Walk over all urls, if they have an http endpoint, check if they have a https one.
        If not: test if there is an https endpoint for certainty.

        If it's still not there, then well... it's points for not having https and http.

        :return:
        """
        # to save ratings
        scan_manager = ScanManager

        # no urls that have endpoints on https that already exist.
        urls = Url.objects.all().filter(is_dead=False,
                                        not_resolvable=False)

        # todo: haven't got the queryset logic down to filter like below. Could be just one query.
        for url in urls:
            logger.debug("Checking for http only sites on: %s" % url)
            endpoints = Endpoint.objects.all().filter(url=url, is_dead=False)

            has_http = False
            has_https = False
            http_endpoints = []

            for endpoint in endpoints:
                if endpoint.protocol == "http":
                    has_http = True
                    http_endpoints.append(endpoint)
                if endpoint.protocol == "https":
                    has_https = True

            # calculate the score
            # Organizations with wildcards can have this problem a lot:
            # 1: It's not possible to distinguish the default page with another page, wildcards
            #    can help hide domains and services.
            # 2: A wildcard TLS connection is an option: then it will be fine, and it can be also
            #    run only on everything that is NOT another service on the server: also hiding stuff
            # 3: Due to SNI it's not possible where something is served.

            # !!! The only solution is to have a "curated" list of port 80 websites. !!!

            # Comparing with screenshots is simply not effective enough:
            # 1: Many HTTPS sites load HTTP resources, which don't show, and thus it's different.
            # 2: There is no guarantee that a wildcard serves a blank page.
            # 3: In the transition phase to default https (coming years), it's not possible to say
            #    what should be the "leading" site.

            # Some organizations redirect the http site to a non-standard https port.
            # occurs more than once... you still have to follow redirects?
            if has_http and not has_https:
                logger.debug("This url seems to have no https at all: %s" % url)
                logger.debug("Checking if they exist, to be sure there is nothing.")

                if not ScannerPlainHttp.verify_is_secure(url):
                    logger.info("%s does not have a https site. Saving/updating scan." % url)
                    for http_endpoint in http_endpoints:
                        scan_manager.add_scan("plain_https", http_endpoint, 200,
                                              "No secure website found, "
                                              "while an insecure website exists on the default "
                                              "port.")

    @staticmethod
    def verify_is_secure(url):
        # i've seen qualys saying there is no TLS, while there is!
        # This _might_ revive an endpoint.
        s = ScannerHttp()

        s.scan_url_list([url], 443, 'https')

        endpoints = Endpoint.objects.all().filter(url=url, is_dead=False,
                                                  protocol="https", port=443)
        if endpoints:
            return True
        return False


class ScanManager:
    """
    Helps with data deduplication of scans. Helps storing scans in a more generic way.

    :return:
    """
    @staticmethod
    def add_scan(scantype, endpoint, rating, message):
        from .models import EndpointGenericScan

        # Check if the latest scan has the same rating or not:
        try:
            gs = EndpointGenericScan.objects.all().filter(
                type=scantype,
                endpoint=endpoint,
            ).latest('last_scan_moment')
        except ObjectDoesNotExist:
            gs = EndpointGenericScan()

        # last scan had exactly the same result, so don't create a new scan and just update the
        # last scan date.
        if gs.explanation == message and gs.rating == rating:
            gs.last_scan_moment = datetime.now(pytz.utc)
            gs.save()
        else:
            gs.explanation = message
            gs.rating = rating
            gs.endpoint = endpoint
            gs.type = scantype
            gs.last_scan_moment = datetime.now(pytz.utc)
            gs.rating_determined_on = datetime.now(pytz.utc)
            gs.save()
