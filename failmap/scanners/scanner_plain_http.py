"""
Check if a domain is only reachable on plain http, instead of both http and https.

Browsers first connect to http, not https when entering a domain. That will be changed in the future.

Further reading:
https://stackoverflow.com/questions/20475552/python-requests-library-redirect-new-url#20475712
"""
import logging

from celery import Task, group

from failmap.organizations.models import Organization, Url
from failmap.scanners.endpoint_scan_manager import EndpointScanManager
from failmap.scanners.scanner_http import redirects_to_safety, verify_is_secure

from ..celery import app
from .models import Endpoint

log = logging.getLogger(__package__)


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    """Compose taskset to scan specified endpoints.

    :param organizations_filter: dict: limit organizations to scan to these filters, see below
    :param urls_filter: dict: limit urls to scan to these filters, see below
    :param endpoints_filter: dict: limit endpoints to scan to these filters, see below

    Depending on the type of scanner (endpoint, domain level, etc) a list of scanable
    items will be generated and a taskset will be composed to allow scanning of these items.

    By default all elegible items will be scanned. Which means a complete scan of everything possible
    with this scanner.

    By specifying filters the list of items to scan can be reduced. These filters are passed to
    Django QuerySet filters on the respective models.

    For example, to scan all urls/endpoints for one organization named 'example' run:

    >>> task = compose_task(organizations={'name__iexact': 'example'})
    >>> result = task.apply_async()
    >>> print(result.get())

    (`name__iexact` matches the name case-insensitive)

    Multiple filters can be applied, to scan only port 80 for organizations added today run:

    >>> task = compose_task(
    ...     organizations={'date_added__day': datetime.datetime.today().day},
    ...     endpoints={'port': 80}
    ... )

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

    if endpoints_filter:
        raise NotImplementedError('This scanner needs to be refactored to scan per endpoint.')

    if not urls:
        raise Exception('Applied filters resulted in no tasks!')

    log.info('Creating scan task %s urls for %s organizations.', len(urls), len(organizations))

    # create tasks for scanning all selected endpoints as a single managable group
    task = group(scan_url.s(url) for url in urls)

    return task


# This needs to be refactored to move the Endpoint iteration to `compose_task`
# and split this task up in a scan and store task so scans can be performed more
# distributed. For examples see scan_dummy.py

# http://185.3.211.120:80: Host: demo3.data.amsterdam.nl Status: 301
@app.task
def scan_url(url: Url):
    """

    :param url:
    :return:
    """

    scan_manager = EndpointScanManager
    log.debug("Checking for http only sites on: %s" % url)
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
        log.debug("This url seems to have no https at all: %s" % url)
        log.debug("Checking if they exist, to be sure there is nothing.")

        # todo: doesn't work anymore, as it's async
        # quick fix: run it again after the discovery tasks have finished.
        if not verify_is_secure(http_v4_endpoint):

            log.info("Checking if the URL redirects to a secure url: %s" % url)
            if redirects_to_safety(http_v4_endpoint):
                log.info("%s redirects to safety, saved by the bell." % url)
                scan_manager.add_scan("plain_https", http_v4_endpoint, "25", saved_by_the_bell)

            else:
                log.info("%s does not have a https site. Saving/updating scan." % url)
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
