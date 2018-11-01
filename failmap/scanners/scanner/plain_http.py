"""
Check if a domain is only reachable on plain http, instead of both http and https.

Browsers first connect to http, not https when entering a domain. That will be changed in the future.

Further reading:
https://stackoverflow.com/questions/20475552/python-requests-library-redirect-new-url#20475712
"""
import logging

from celery import Task, group

from failmap.celery import app
from failmap.organizations.models import Organization, Url
from failmap.scanners.models import Endpoint
from failmap.scanners.scanmanager.endpoint_scan_manager import EndpointScanManager
from failmap.scanners.scanner.http import (can_connect, connect_result, redirects_to_safety,
                                           resolves_on_v4, resolves_on_v6)
from failmap.scanners.scanner.scanner import allowed_to_scan, q_configurations_to_scan

log = logging.getLogger(__package__)

# These messages are translated and expected lateron. Don't edit them unless you're also editing them in the reporting
# etc etc.
cleaned_up = "Has a secure equivalent, which wasn't so in the past."
not_resolvable_at_all = "Cannot be resolved anymore, seems to be cleaned up."
saved_by_the_bell = "Redirects to a secure site, while a secure counterpart on the standard port is missing."
no_https_at_all = "Site does not redirect to secure url, and has no secure alternative on a standard port."


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
    **kwargs
) -> Task:

    # We might not be allowed to scan for this at all.
    if not allowed_to_scan("scanner_plain_http"):
        return group()  # An empty group fits this callable's signature and does not impede celery.

    if organizations_filter:
        organizations = Organization.objects.filter(is_dead=False, **organizations_filter)
        urls = Url.objects.filter(q_configurations_to_scan(),
                                  organization__in=organizations, is_dead=False, not_resolvable=False, **urls_filter)
        log.info('Creating scan task %s urls for %s organizations.', len(urls), len(organizations))
    else:
        urls = Url.objects.filter(q_configurations_to_scan(), is_dead=False, not_resolvable=False, **urls_filter)
        log.info('Creating scan plain http task %s urls.', len(urls))

    if endpoints_filter:
        raise NotImplementedError('This scanner needs to be refactored to scan per endpoint.')

    if not urls:
        log.warning('Applied filters resulted in no urls, thus no plain http tasks!')
        return group()

    tasks = []
    for url in urls:
        complete_endpoints, incomplete_endpoints = get_endpoints_with_missing_encryption(url)

        for complete_endpoint in complete_endpoints:
            tasks.append(well_done.si(complete_endpoint))

        for incomplete_endpoint in incomplete_endpoints:
            queue = "ipv4" if incomplete_endpoint.ip_version == 4 else "ipv6"
            tasks.append(scan.si(incomplete_endpoint).set(queue=queue) | store.s(incomplete_endpoint))

    return group(tasks)


@app.task(queue='storage')
def get_endpoints_with_missing_encryption(url):
    """
    Finds a list of endpoints that are missing an encrypted counterpart. Takes in account ip_version.

    The default ports matter for normal humans. All services on other ports are special services.
    we only give points if there is not a normal https site when there is a normal http site.
    :param url:
    :return:
    """

    endpoints = Endpoint.objects.all().filter(url=url, is_dead=False)

    has_http_v4, has_https_v4, has_http_v6, has_https_v6 = False, False, False, False
    http_v4_endpoint, http_v6_endpoint = None, None
    complete_endpoints, incomplete_endpoints = [], []

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

    if has_http_v4 and not has_https_v4:
        incomplete_endpoints.append(http_v4_endpoint)

    if has_http_v4 and has_https_v4:
        complete_endpoints.append(http_v4_endpoint)

    if has_http_v6 and not has_https_v6:
        incomplete_endpoints.append(http_v6_endpoint)

    if has_http_v6 and has_https_v6:
        complete_endpoints.append(http_v6_endpoint)

    return complete_endpoints, incomplete_endpoints


@app.task(queue='storage')
def well_done(endpoint):
    if EndpointScanManager.had_scan_with_points("plain_https", endpoint):
        EndpointScanManager.add_scan("plain_https", endpoint, "0", cleaned_up)


# Task is written to work both on v4 and v6, but the network conf of the machine differs.
@app.task()
def scan(endpoint):
    """
    Using an incomplete endpoint

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

    :param endpoint:
    :return:
    """

    # if the address doesn't resolve, why bother scanning at all?
    resolves = False
    if endpoint.ip_version == 4:
        resolves = resolves_on_v4(endpoint.url.url)
    if endpoint.ip_version == 6:
        resolves = resolves_on_v6(endpoint.url.url)

    if not resolves:
        # no need to further check, can't even get the IP address...
        return False, False, False

    can_connect_result = can_connect(protocol="https", url=endpoint.url, port=443, ip_version=endpoint.ip_version)
    redirects_to_safety_result = None

    # if you cannot connect to a secure endpoint, we're going to find out of there is redirect.
    if not can_connect_result:
        redirects_to_safety_result = redirects_to_safety(endpoint)

    return resolves, can_connect_result, redirects_to_safety_result


@app.task(queue='storage')
def store(results, endpoint):

    resolves, can_connect_result, redirects_to_safety_result = results

    if not resolves:
        # Don't administrate endpoints that don't resolve, that is a task for the http verify scanner. Here we just
        # don't try to redirect to safety or otherwise miscalculate the result. If the http verify scanner is not run
        # there will be mismatches between this (or previous results) and reality.
        log.debug("Endpoint on %s doesn't resolve anymore. "
                  "Run the DNS verify scanner to prevent scanning non resolving endpoints." % endpoint)
        return

    connect_result(can_connect_result, protocol="https", url=endpoint.url, port=443, ip_version=endpoint.ip_version)

    # issue resolved.
    if can_connect_result:
        if EndpointScanManager.had_scan_with_points("plain_https", endpoint):
            EndpointScanManager.add_scan("plain_https", endpoint, "0", cleaned_up)

    # Really no security at all
    if not can_connect_result and redirects_to_safety_result is False:
        log.info("%s does not have a https site. Saving/updating scan." % endpoint.url)
        EndpointScanManager.add_scan("plain_https", endpoint, "1000", no_https_at_all)

    # some redirections that might have flaws etc.
    if not can_connect_result and redirects_to_safety_result is True:
        log.info("%s redirects to safety, saved by the bell." % endpoint.url)
        EndpointScanManager.add_scan("plain_https", endpoint, "25", saved_by_the_bell)
