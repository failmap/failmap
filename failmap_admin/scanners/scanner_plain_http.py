"""
Check if a domain is only reachable on plain http, instead of both http and https.

Browsers first connect to http, not https when entering a domain. That will be changed in the future.


Testing:
redis-cli flushdb


Further reading:
https://stackoverflow.com/questions/20475552/python-requests-library-redirect-new-url#20475712
"""
import logging
from typing import List

from celery import group

from failmap_admin.organizations.models import Url
from failmap_admin.scanners.endpoint_scan_manager import EndpointScanManager
from failmap_admin.scanners.scanner_http import redirects_to_safety, verify_is_secure

from ..celery import app
from .models import Endpoint

logger = logging.getLogger(__package__)


def scan_all_urls():
    """
    Walk over all urls, if they have an http endpoint, check if they have a https one.
    If not: test if there is an https endpoint for certainty.

    If it's still not there, then well... it's points for not having https and http.

    todo: how to remove entries from this list?


    :return:
    """
    # to save ratings

    # no urls that have endpoints on https that already exist.
    urls = Url.objects.all().filter(is_dead=False,
                                    not_resolvable=False)

    scan_urls(urls=list(urls), execute=True)


def scan_urls(urls: List[Url], execute: bool=True):
    """
    Scans all urls, including the entire list that is in the endpoint-generic scan list (existing problems) for missing
    https on the default port.

    :param urls:
    :param execute: Boolean
    :return:
    """
    task = group([scan_url.s(url) for url in urls])
    if execute:
        task.apply_async()
    else:
        return task


# http://185.3.211.120:80: Host: demo3.data.amsterdam.nl Status: 301
@app.task
def scan_url(url: Url):
    """

    :param url:
    :return:
    """

    scan_manager = EndpointScanManager
    logger.debug("Checking for http only sites on: %s" % url)
    endpoints = Endpoint.objects.all().filter(url=url, is_dead=False)

    has_http_v4 = False
    has_https_v4 = False
    has_http_v6 = False
    has_https_v6 = False
    http_v4_endpoint = None
    http_v6_endpoint = None

    saved_by_the_bell = "Redirects to a secure site, while a secure counterpart on the standard port is missing."
    no_https_at_all = "Site does not redirect to secure url, and has no secure alternative on a standard port."
    cleaned_up = "Has a secure equivalent, which wasn't so in the past."

    # The default ports matter for normal humans. All services on other ports are special services.
    # we only give points if there is not a normal https site when there is a normal http site.

    for endpoint in endpoints:
        if endpoint.protocol == "http" and endpoint.port == 80 and endpoint.ip_version == 4:
            has_http_v4 = True
            http_v4_endpoint = endpoint
        if endpoint.protocol == "https" and endpoint.port == 443 and endpoint.ip_version == 4:
            has_https_v4 = True

        if endpoint.protocol == "http" and endpoint.port == 80 and endpoint.ip_version == 6:
            has_http_v6 = True
            http_v6_endpoint = endpoint

        if endpoint.protocol == "https" and endpoint.port == 443 and endpoint.ip_version == 6:
            has_https_v6 = True

    # calculate the score
    # Organizations with wildcards can have this problem a lot:
    # 1: It's not possible to distinguish the default page with another page, wildcards
    #    can help hide domains and services.
    # 2: A wildcard TLS connection is an option: then it will be fine, and it can be also
    #    run only on everything that is NOT another service on the server: also hiding stuff
    # 3: Due to SNI it's not possible where something is served.

    # !!! The only solution is to have a "curated" list of port 80 websites. !!!
    # maybe compare an image of a non existing url with the random ones given here.
    # if they are the same, then there is really no site. That should help clean
    # non-existing wildcard domains.

    # Comparing with screenshots is simply not effective enough:
    # 1: Many HTTPS sites load HTTP resources, which don't show, and thus it's different.
    # 2: There is no guarantee that a wildcard serves a blank page.
    # 3: In the transition phase to default https (coming years), it's not possible to say
    #    what should be the "leading" site.

    # Some organizations redirect the http site to a non-standard https port.
    # occurs more than once... you still have to follow redirects?
    if has_http_v4 and not has_https_v4:
        logger.debug("This url seems to have no https at all: %s" % url)
        logger.debug("Checking if they exist, to be sure there is nothing.")

        # todo: doesn't work anymore, as it's async
        # quick fix: run it again after the discovery tasks have finished.
        if not verify_is_secure(http_v4_endpoint):

            logger.info("Checking if the URL redirects to a secure url: %s" % url)
            if redirects_to_safety(http_v4_endpoint):
                logger.info("%s redirects to safety, saved by the bell." % url)
                scan_manager.add_scan("plain_https", http_v4_endpoint, "25", saved_by_the_bell)

            else:
                logger.info("%s does not have a https site. Saving/updating scan." % url)
                scan_manager.add_scan("plain_https", http_v4_endpoint, "1000", no_https_at_all)
    else:
        # it is secure, and if there was a rating, then reduce it to 0 (with a new rating).
        if scan_manager.had_scan_with_points("plain_https", http_v4_endpoint):
            scan_manager.add_scan("plain_https", http_v4_endpoint, "0", cleaned_up)

    if has_http_v6 and not has_https_v6:
        if not verify_is_secure(http_v6_endpoint):
            if redirects_to_safety(http_v6_endpoint):
                scan_manager.add_scan("plain_https", http_v6_endpoint, "25", saved_by_the_bell)
            else:
                scan_manager.add_scan("plain_https", http_v6_endpoint, "1000", no_https_at_all)
    else:
        # it is secure, and if there was a rating, then reduce it to 0 (with a new rating).
        if scan_manager.had_scan_with_points("plain_https", http_v6_endpoint):
            scan_manager.add_scan("plain_https", http_v6_endpoint, "0", cleaned_up)

    return 'done'
