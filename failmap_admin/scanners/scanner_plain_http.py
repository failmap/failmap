"""
Check if a domain is only reachable on plain http, instead of both http and https

Browsers first connect to http, not https when entering a domain. That will be changed in the
future.

"""
import logging

from failmap_admin.organizations.models import Url
from failmap_admin.scanners.endpoint_scan_manager import EndpointScanManager
from failmap_admin.scanners.scanner_http import scan_urls as scanner_http_scan_urls

from .models import Endpoint

logger = logging.getLogger(__package__)


def scan_all_urls():
    """
    Walk over all urls, if they have an http endpoint, check if they have a https one.
    If not: test if there is an https endpoint for certainty.

    If it's still not there, then well... it's points for not having https and http.

    :return:
    """
    # to save ratings

    # no urls that have endpoints on https that already exist.
    urls = Url.objects.all().filter(is_dead=False,
                                    not_resolvable=False)

    # todo: haven't got the queryset logic down to filter like below. Could be just one query.
    for url in urls:
        scan_url(url)


def scan_urls(urls):
    for url in urls:
        scan_url(url)


def scan_url(url):
    scan_manager = EndpointScanManager
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
    if has_http and not has_https:
        logger.debug("This url seems to have no https at all: %s" % url)
        logger.debug("Checking if they exist, to be sure there is nothing.")

        # It's not secure initially, do a last check. This might result in new
        # endpoints, and therefore no scan record.
        # todo: hm, you can't really check ipv6 redirects on an ipv4 box, now can you...
        if not verify_is_secure(url):

            logger.info("Checking if the URL redirects to a secure url: %s" % url)
            if redirects_to_safety(url):
                logger.info("%s redirects to safety, saved by the bell." % url)
                for http_endpoint in http_endpoints:
                    scan_manager.add_scan("plain_https", http_endpoint, 25,
                                          "Redirects to a secure site, while a secure "
                                          "counterpart on the standard port is missing.")

            else:
                logger.info("%s does not have a https site. Saving/updating scan." % url)
                for http_endpoint in http_endpoints:
                    scan_manager.add_scan("plain_https", http_endpoint, 1000,
                                          "Site does not redirect to secure url, and has no"
                                          "secure alternative on a standard port.")
        else:
            # it is secure, and if there was a rating, then reduce it to 0
            # (with a new rating).
            for http_endpoint in http_endpoints:
                if scan_manager.had_scan_with_points("plain_https", http_endpoint):
                    scan_manager.add_scan("plain_https", http_endpoint, 0,
                                          "Has a secure equivalent, which wasn't so in the"
                                          "past.")


def verify_is_secure(url):
    # i've seen qualys saying there is no TLS, while there is!
    # This _might_ revive an endpoint.
    scanner_http_scan_urls([url], [443], ['https'])

    endpoints = Endpoint.objects.all().filter(url=url, is_dead=False,
                                              protocol="https", port=443)
    if endpoints:
        logger.debug("Url does seem to be secure after all: %s" % url)
        return True
    logger.debug("Url is still not secure: %s" % url)
    return False

# https://stackoverflow.com/questions/20475552/python-requests-library-redirect-new-url#20475712


def redirects_to_safety(url):
    import requests
    from requests import ReadTimeout, ConnectTimeout, HTTPError, Timeout, ConnectionError
    domain = "%s://%s:%s" % ("http", url.url, "80")
    try:
        response = requests.get(domain, timeout=(10, 10), allow_redirects=True)
        if response.history:
            logger.debug("Request was redirected, there is hope. Redirect path:")
            for resp in response.history:
                logger.debug("%s: %s" % (resp.status_code, resp.url))
            logger.debug("Final destination:")
            logger.debug("%s: %s" % (response.status_code, response.url))
            if response.url.startswith("https://"):
                logger.debug("Url starts with https, so it redirects to safety.")
                return True
            logger.debug("Url is not redirecting to a safe url.")
            return False
        else:
            logger.debug("Request was not redirected, so not going to a safe url.")
            return False
    except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError):
        logger.debug("Request resulted into an error, it's not redirecting properly.")
        return False
