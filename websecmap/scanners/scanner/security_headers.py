"""
Check if the https site uses HSTS to tell the browser the site should only be reached over HTTPS.
(useful until browsers do https by default, instead of by choice)
"""
import logging
from datetime import datetime

import pytz
import requests
import urllib3
from celery import Task, group
from requests import ConnectionError, ConnectTimeout, HTTPError, ReadTimeout, Timeout

from websecmap.celery import ParentFailed, app
from websecmap.organizations.models import Organization, Url
from websecmap.scanners.models import Endpoint, EndpointGenericScanScratchpad
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.__init__ import allowed_to_scan, q_configurations_to_scan
from websecmap.scanners.scanner.http import get_random_user_agent

log = logging.getLogger(__name__)


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
    **kwargs
) -> Task:
    """Compose taskset to scan specified endpoints.
    """

    if not allowed_to_scan("security_headers"):
        return group()

    # apply filter to organizations (or if no filter, all organizations)
    # apply filter to urls in organizations (or if no filter, all urls)
    organizations = []
    if organizations_filter:
        organizations = Organization.objects.filter(**organizations_filter)
        urls = Url.objects.filter(q_configurations_to_scan(), organization__in=organizations, **urls_filter)
        log.info('Creating header scan task for %s urls for %s organizations.', len(urls), len(organizations))
    else:
        urls = Url.objects.filter(q_configurations_to_scan(), **urls_filter)
        log.info('Creating header scan task for %s urls.', len(urls))

    # select endpoints to scan based on filters
    endpoints = Endpoint.objects.filter(
        # apply filter to endpoints (or if no filter, all endpoints)
        url__in=urls, **endpoints_filter,
        # also apply mandatory filters to only select valid endpoints for this action
        is_dead=False, protocol__in=['http', 'https'])

    if not endpoints:
        log.warning('Security headers: Applied filters resulted in no tasks! organisations_filter %s, '
                    'URL Filter: %s, endpoints_filter: %s', organizations_filter, urls_filter, endpoints_filter)
        return group()

    # unique endpoints only
    endpoints = list(set(endpoints))

    log.info('Creating security headers scan task for %s endpoints for %s urls for %s organizations.',
             len(endpoints), len(urls), len(organizations))

    tasks = []
    for endpoint in endpoints:
        queue = "ipv4" if endpoint.ip_version == 4 else "ipv6"
        tasks.append(get_headers.si(endpoint.uri_url()).set(queue=queue) | analyze_headers.s(endpoint))

    log.info("Created %s tasks" % len(tasks))

    return group(tasks)


@app.task(queue="storage")
def analyze_headers(result: requests.Response, endpoint):
    # todo: remove code paths, and make a more clear case per header type. That's easier to understand edge cases.
    # todo: Content-Security-Policy, Referrer-Policy

    # if scan task failed, ignore the result (exception) and report failed status
    if isinstance(result, Exception):
        return ParentFailed('Skipping http header result parsing because scan failed.', cause=result)

    response = result

    # scratch it, for debugging.
    egss = EndpointGenericScanScratchpad()
    egss.at_when = datetime.now(pytz.utc)
    egss.data = "Status: %s, Headers: %s, Redirects: %s" % (response.status_code, response.headers, response.history)
    egss.type = "security headers"
    egss.save()

    """
    #125: CSP can replace X-XSS-Protection and X-Frame-Options. Thus if a (more modern) CSP header is present, assume
    that decisions have been made about what's in it and ignore the previously mentioned headers.

    We don't mandate CSP yet because it's utterly complex and therefore comes with an extremely low adoption ratio.

    https://stackoverflow.com/questions/43039706/replacing-x-frame-options-with-csp
    X-Frame-Options: SAMEORIGIN ➡ Content-Security-Policy: frame-ancestors 'self'

    https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-XSS-Protection
    X-XSS-Protection -> ('unsafe-inline')

    X-Content-Type-Options is not affected.
    """

    # We've removed conditional scans in scannerss, as more scan data is better.
    # you can cohose not to display or report it. Below used to be conditional scans.

    generic_check_using_csp_fallback(endpoint, response.headers, 'X-XSS-Protection')
    generic_check_using_csp_fallback(endpoint, response.headers, 'X-Frame-Options')
    generic_check(endpoint, response.headers, 'X-Content-Type-Options')

    """
    https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security
    Note: The Strict-Transport-Security header is ignored by the browser when your site is accessed using HTTP;
    this is because an attacker may intercept HTTP connections and inject the header or remove it.  When your
    site is accessed over HTTPS with no certificate errors, the browser knows your site is HTTPS capable and will
    honor the Strict-Transport-Security header.

    7 march 2018
    After a series of complaints of products designed specifically to run on port 443 (without any non-secured port)
    we've decided that HSTS is only required if there are no unsecured (http) endpoints on this url.
    This means: if you still run (another) service on an unsecured http port, we're still demanding hsts. We're not
    able to see what product runs on what port (and it should be like that).

    The HSTS header is a sloppy patch job anyway, it will be phased out after browsers require sites to run on 443 and
    just start blocking port 80 for websites alltogether. On that day preloading also goes out the window.

    It basically works like this:
    A downgrade attack is not dependent on missing hsts. It's depending on who operates the network and if they employ
    DNS cache poisoning and use sslstrip etc. Then it comes down to your browser not accepting http at all either via
    preloading or the HSTS header (or design). The user may also trust your injected certificate given HPKP is removed
    everywhere and users will certainly click OK if they can.

    If you think it works differently, just file an issue or make a pull request. We want to get it right.
    """
    if endpoint.protocol == "https":

        # runs any unsecured http service? (on ANY port).
        unsecure_services = Endpoint.objects.all().filter(url=endpoint.url, protocol="http", is_dead=False).exists()
        if unsecure_services:
            generic_check(endpoint, response.headers, 'Strict-Transport-Security')
        else:
            if 'Strict-Transport-Security' in response.headers:
                log.debug('Has Strict-Transport-Security')
                store_endpoint_scan_result('http_security_header_strict_transport_security', endpoint, 'True',
                                           response.headers['Strict-Transport-Security'])
            else:
                log.debug('Has no Strict-Transport-Security, yet offers no insecure http service.')
                store_endpoint_scan_result('http_security_header_strict_transport_security', endpoint, 'False',
                                           "Security Header not present: Strict-Transport-Security, "
                                           "yet offers no insecure http service.")

    return {'status': 'success'}


def generic_check(endpoint: Endpoint, headers, header):
    # this is case insensitive

    scan_type = "http_security_header_%s" % header.lower().replace("-", "_")

    if header in headers.keys():
        log.debug('Has %s' % header)
        store_endpoint_scan_result(scan_type, endpoint, 'True', headers[header])
    else:
        log.debug('Has no %s' % header)
        store_endpoint_scan_result(scan_type, endpoint, 'False', "Security Header not present: %s" % header)


def generic_check_using_csp_fallback(endpoint: Endpoint, headers, header):
    scan_type = "http_security_header_%s" % header.lower().replace("-", "_")

    # this is case insensitive
    if header in headers.keys():
        log.debug('Has %s' % header)
        store_endpoint_scan_result(scan_type, endpoint, 'True', headers[header])
    else:
        # CSP fallback:
        log.debug('CSP fallback used for %s' % header)
        if "Content-Security-Policy" in headers.keys():
            store_endpoint_scan_result(
                scan_type=scan_type,
                endpoint=endpoint,
                rating='Using CSP',
                message="Content-Security-Policy header found, which can handle the security from %s."
                        "Value (possibly truncated): %s..." %
                        (header, headers["Content-Security-Policy"][0:80]),
                evidence=headers["Content-Security-Policy"]
            )

        else:
            log.debug('Has no %s' % header)
            store_endpoint_scan_result(
                scan_type=scan_type,
                endpoint=endpoint,
                rating='False',
                message="Security Header not present: %s, alternative header Content-Security-Policy not present." %
                        header
            )


@app.task(bind=True, default_retry_delay=1, retry_kwargs={'max_retries': 3})
def get_headers(self, uri_uri):
    try:
        return get_headers_request(uri_uri)

    # The amount of possible return states is overwhelming :)

    # Solving https://sentry.io/internet-cleanup-foundation/faalkaart/issues/460895712/
    #         https://sentry.io/internet-cleanup-foundation/faalkaart/issues/460895699/
    # ValueError, really don't know how to further handle it.
    #
    # Solving https://sentry.io/internet-cleanup-foundation/faalkaart/issues/425503689/
    # requests.TooManyRedirects
    #
    # Solving https://sentry.io/internet-cleanup-foundation/faalkaart/issues/425507209/
    # LocationValueError - No host specified.
    # it redirects to something like https:/// (with three slashes) and then somewhere it crashes
    # possibly an error in requests.
    #
    # Possibly tooManyRedirects could be plotted on the map, given this is a configuration error
    except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError, ValueError,
            requests.TooManyRedirects, urllib3.exceptions.LocationValueError) as e:
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


def get_headers_request(uri_url):
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

    Update 17 dec 2018: some web servers require a user agent to be sent in order to give a "more correct" response.
    Given that 'humans with browsers' access these pages, it's normal to also send a user agent.

    :return: requests.response
    """

    log.debug('Getting headers for %s' % uri_url)

    # ignore wrong certificates, those are handled in a different scan.
    # 10 seconds for network delay, 10 seconds for the site to respond.
    response = requests.get(uri_url,
                            timeout=(10, 10),
                            allow_redirects=True,
                            verify=False,
                            headers={'User-Agent': get_random_user_agent()})

    # Removed: only continue for valid responses (eg: 200)
    # Error pages, such as 404 are super fancy, with forms and all kinds of content.
    # it's obvious that such pages (with content) follow the same security rules as any 2XX response.
    # if 400 <= response.status_code <= 600:
    #     error_response_400_500(endpoint)
    # response.raise_for_status()

    for header in response.headers:
        log.debug('Received header: %s' % header)
    return response
