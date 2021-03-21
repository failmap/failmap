"""
Check if the https site uses HSTS to tell the browser the site should only be reached over HTTPS.
(useful until browsers do https by default, instead of by choice)
"""
import logging
from typing import Dict

import requests
import urllib3
from celery import Task, group
from requests import ConnectionError, ConnectTimeout, HTTPError, ReadTimeout, Timeout

from websecmap.celery import ParentFailed, app
from websecmap.organizations.models import Organization, Url
from websecmap.scanners import plannedscan
from websecmap.scanners.models import Endpoint, EndpointGenericScan
from websecmap.scanners.plannedscan import retrieve_endpoints_from_urls
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.__init__ import allowed_to_scan, q_configurations_to_scan, unique_and_random
from websecmap.scanners.scanner.http import get_random_user_agent
from websecmap.scanners.scanner.utils import CELERY_IP_VERSION_QUEUE_NAMES

log = logging.getLogger(__name__)


SECURITY_HEADER_SCAN_TYPES = [
    "http_security_header_strict_transport_security",
    "http_security_header_x_content_type_options",
    "http_security_header_x_frame_options",
    "http_security_header_x_xss_protection",
]


def filter_scan(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
):
    # apply filter to organizations (or if no filter, all organizations)
    # apply filter to urls in organizations (or if no filter, all urls)
    organizations = []
    if organizations_filter:
        organizations = Organization.objects.filter(**organizations_filter).only("id")
        urls = Url.objects.filter(q_configurations_to_scan(), organization__in=organizations, **urls_filter)
    else:
        urls = Url.objects.filter(q_configurations_to_scan(), **urls_filter)

    # We only perform an IN query, and need nothing of these urls except the ID:
    urls = urls.only("id")

    # select endpoints to scan based on filters
    endpoints = Endpoint.objects.filter(
        # apply filter to endpoints (or if no filter, all endpoints)
        url__in=urls,
        **endpoints_filter,
        # also apply mandatory filters to only select valid endpoints for this action
        is_dead=False,
        protocol__in=["http", "https"],
    ).only("id", "port", "protocol", "ip_version", "url__id", "url__url")

    # unique endpoints only
    endpoints = unique_and_random(endpoints)
    return unique_and_random([endpoint.url for endpoint in endpoints])


@app.task(queue="storage")
def plan_scan(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
):
    if not allowed_to_scan("security_headers"):
        return group()

    urls = filter_scan(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    plannedscan.request(activity="scan", scanner="security_headers", urls=urls)


@app.task(queue="storage")
def compose_planned_scan_task(**kwargs):
    urls = plannedscan.pickup(activity="scan", scanner="security_headers", amount=kwargs.get("amount", 25))
    return compose_scan_task(urls)


def compose_manual_scan_task(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
) -> Task:
    """Compose taskset to scan specified endpoints."""
    if not allowed_to_scan("security_headers"):
        return group()

    urls = filter_scan(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    return compose_scan_task(urls)


def compose_scan_task(urls):
    endpoints = retrieve_endpoints_from_urls(urls, protocols=["http", "https"])

    endpoints = unique_and_random(endpoints)
    log.info(f"Scanning security headers on {len(endpoints)} endpoints, {len(urls)} urls")

    tasks = []
    for endpoint in endpoints:
        tasks.append(
            get_headers.si(endpoint.uri_url()).set(queue=CELERY_IP_VERSION_QUEUE_NAMES[endpoint.ip_version])
            | analyze_headers.s(endpoint)
            | plannedscan.finish.si("scan", "security_headers", endpoint.url)
        )

    return group(tasks)


def discover_service_type(headers: Dict = None):
    """
    Try to discover some meaning of the webserver headers, because some HTTP servers are used for entirely different
    purposes than hosting web pages. For example SOAP is used for XML messages and has their own security paradigm.

    :param headers:
    :return:
    """
    if not headers:
        log.debug("No headers present, falling back to service type HTTP.")
        return "HTTP"

    # Soap messages, they don't need any standard http web headers at all.
    # known are: X-WSSecurity-Enabled, X-WSSecurity-For, X-OAuth-Enabled, WWW-Authenticate
    # We trust that this header is not just set to circumvent HTTP security checks in the meanwhile.
    # Soap security checks are harder, and headers are much harder to implement correctly.
    if "X-SOAP-Enabled" in headers:
        log.debug("Service type to be discovered as: SOAP.")
        return "SOAP"

    # Do not assume headers for sites with Basic Authentication and login portals. The application behind the
    # login can set the headers to whatever it sees fit. Connecting those sites to the internet is still stupid,
    # but there's probably a reason for it.
    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/WWW-Authenticate
    # https://www.iana.org/assignments/http-authschemes/http-authschemes.xhtml
    # In the future we _CAN_ however list insecure authentication methods as such, meaning getting rid of
    # basic authentication.
    if "www-authenticate" in headers:
        log.debug("Authentication required to discover headers. Reporting this as unknown.")
        return "RESTRICTED"

    # We're going to ignore all service types, except whatever looks like html/xhtml/etc
    # So text/plain, text/json and such are ignored.
    content_type = headers.get("Content-Type", "UNKNOWN")
    html_content_types = [
        "text/html; charset=utf-8",
        "text/html",
        "application/xhtml+xml",
        "application/xhtml",
        "html",
        "htm",
        "xhtml",
        "application/xhtml + xml",
        "text/html;charset=utf-8",
    ]

    # text/html can have many charsets, such as us-ascii.
    if content_type.lower() in html_content_types or "text/html" in content_type.lower():
        return "HTTP"

    log.debug("Unknown service type discovered.")
    return "UNKNOWN"


@app.task(queue="storage")
def analyze_headers(result: requests.Response, endpoint):
    # todo: remove code paths, and make a more clear case per header type. That's easier to understand edge cases.
    # todo: Content-Security-Policy, Referrer-Policy

    # if scan task failed, ignore the result (exception) and report failed status
    if isinstance(result, Exception):
        """
        There could be many reason the parent failed. Some issues however are created by mandated certificate use.
        In this case a "ConnectionError", "('Connection aborted.', OSError(\"(104, 'ECONNRESET')\",)) is received.
        An active connection reset indicates that you'll not be ever able to update scan results.

        This is a nice edge case, since the endpoint still exist and the certificate is also valid. But the
        headers cannot ever be retrieved. This causes header information to be outdated for months or years.

        For this case another state had been defined: unreachable. This is a header state that is seen as good. It
        will be applied to all existing headers of this endpoint, in order to clean up what is already there.

        """

        existing_header_scans = EndpointGenericScan.objects.all().filter(
            endpoint=endpoint, type__in=SECURITY_HEADER_SCAN_TYPES, is_the_latest_scan=True
        )

        # Do not store 'corrections' when there are no scans already.
        if not existing_header_scans:
            return ParentFailed("Skipping http header result parsing because scan failed.", cause=result)

        # There used to be stringent filtering here: for oserror and ECONNRESET in the exception, but the fact is
        # that there are so many possible network errors, that it's always a struggle to keep up to date.
        # Instead of handling every edge case, make sure that the existing headers are set to unreachable,
        # and that the evidence shows what went wrong for later debugging reasons.

        for scan in existing_header_scans:
            store_endpoint_scan_result(scan.type, endpoint, "Unreachable", "Address became unreachable.", str(result))

        return {"status": "success"}

    response = result

    # determine what kind of service we're dealing with.
    service_type = discover_service_type(response.headers)

    if service_type == "HTTP":
        return analyze_website_headers(endpoint, response)
    if service_type == "SOAP":
        return analyze_soap_headers(endpoint, response)
    if service_type == "UNKNOWN":
        return clean_up_existing_headers(endpoint, response, service_type=service_type, reason="unknown_content_type")
    if service_type == "RESTRICTED":
        return clean_up_existing_headers(
            endpoint, response, service_type=service_type, reason="authentication_required"
        )


def analyze_soap_headers(endpoint, response):
    """
    We currently have no implementation for SOAP headers, but we do know that previously discovered non-soap headers
    can be overwritten as being SOAP headers and not being relevant anymore.

    There is no implementation for checking the security of soap headers, although a soap service should be using
    some of the following: X-WSSecurity-Enabled, X-WSSecurity-For, X-OAuth-Enabled, WWW-Authenticate

    A next iteration of websecmap could/should contain this validation that certain headers are mandated for SOAP.

    :param endpoint:
    :param response:
    :return:
    """

    # clean up existing web headers and set them to being not relevant for soap:
    existing_header_scans = EndpointGenericScan.objects.all().filter(
        endpoint=endpoint, type__in=SECURITY_HEADER_SCAN_TYPES, is_the_latest_scan=True
    )

    for scan in existing_header_scans:
        store_endpoint_scan_result(scan.type, endpoint, "SOAP", "Header not relevant for SOAP service.")

    return {"status": "success"}


def clean_up_existing_headers(endpoint, response, service_type: str, reason: str):
    """
    Unknown headers for a content type we can't handle.

    We do NOT create new headers, meaning that if no relevant data was found, no records are added to the database.

    :param endpoint:
    :param response:
    :param service_type: What type of service has been discovered that prevents further processing: RESTRICTED, UNKNOWN
    :param reason: More verbose explanation of the service type.
    :return:
    """

    # clean up existing web headers and set them to being not relevant for soap:
    existing_header_scans = EndpointGenericScan.objects.all().filter(
        endpoint=endpoint, type__in=SECURITY_HEADER_SCAN_TYPES, is_the_latest_scan=True
    )

    for scan in existing_header_scans:
        store_endpoint_scan_result(scan.type, endpoint, service_type, reason)

    return {"status": "success"}


def analyze_website_headers(endpoint, response):
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

    generic_check_using_csp_fallback(endpoint, response.headers, "X-XSS-Protection")
    generic_check_using_csp_fallback(endpoint, response.headers, "X-Frame-Options")
    generic_check(endpoint, response.headers, "X-Content-Type-Options")

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
            generic_check(endpoint, response.headers, "Strict-Transport-Security")
        else:
            if "Strict-Transport-Security" in response.headers:
                log.debug("Has Strict-Transport-Security")
                store_endpoint_scan_result(
                    "http_security_header_strict_transport_security",
                    endpoint,
                    "True",
                    response.headers["Strict-Transport-Security"],
                )
            else:
                log.debug("Has no Strict-Transport-Security, yet offers no insecure http service.")
                store_endpoint_scan_result(
                    "http_security_header_strict_transport_security",
                    endpoint,
                    "False",
                    "Security Header not present: Strict-Transport-Security, " "yet offers no insecure http service.",
                )

    return {"status": "success"}


def generic_check(endpoint: Endpoint, headers, header):
    # this is case insensitive

    scan_type = "http_security_header_%s" % header.lower().replace("-", "_")

    if header in headers.keys():
        log.debug("Has %s" % header)
        store_endpoint_scan_result(scan_type, endpoint, "True", headers[header])
    else:
        log.debug("Has no %s" % header)
        store_endpoint_scan_result(scan_type, endpoint, "False", "Security Header not present: %s" % header)


def generic_check_using_csp_fallback(endpoint: Endpoint, headers, header):
    scan_type = "http_security_header_%s" % header.lower().replace("-", "_")

    # this is case insensitive
    if header in headers.keys():
        log.debug("Has %s" % header)
        store_endpoint_scan_result(scan_type, endpoint, "True", headers[header])
    else:
        # CSP fallback:
        log.debug("CSP fallback used for %s" % header)
        if "Content-Security-Policy" in headers.keys():
            store_endpoint_scan_result(
                scan_type=scan_type,
                endpoint=endpoint,
                rating="Using CSP",
                message="Content-Security-Policy header found, which can handle the security from %s."
                "Value (possibly truncated): %s..." % (header, headers["Content-Security-Policy"][0:80]),
                evidence=headers["Content-Security-Policy"],
            )

        else:
            log.debug("Has no %s" % header)
            store_endpoint_scan_result(
                scan_type=scan_type,
                endpoint=endpoint,
                rating="False",
                message="Security Header not present: %s, alternative header Content-Security-Policy not present."
                % header,
            )


@app.task(bind=True, default_retry_delay=1, retry_kwargs={"max_retries": 3})
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
    except (
        ConnectTimeout,
        HTTPError,
        ReadTimeout,
        Timeout,
        ConnectionError,
        ValueError,
        requests.TooManyRedirects,
        urllib3.exceptions.LocationValueError,
    ) as e:
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

    log.debug("Getting headers for %s" % uri_url)

    # ignore wrong certificates, those are handled in a different scan.
    # 10 seconds for network delay, 10 seconds for the site to respond.
    response = requests.get(
        uri_url,
        timeout=(10, 10),
        allow_redirects=True,
        verify=False,  # nosec TLS does not have to be valid in this test, only headers do.
        headers={"User-Agent": get_random_user_agent()},
    )

    # redirects are followed, this gives an indication on how many redirects are followed, and what url the
    # headers are taken from:
    for index, resp in enumerate(response.history):
        log.debug(f"- Redirect {index}: {resp.url}.")

    log.debug(f"- You are now at {response.url}.")

    # Removed: only continue for valid responses (eg: 200)
    # Error pages, such as 404 are super fancy, with forms and all kinds of content.
    # it's obvious that such pages (with content) follow the same security rules as any 2XX response.
    # if 400 <= response.status_code <= 600:
    #     error_response_400_500(endpoint)
    # response.raise_for_status()

    for header in response.headers:
        log.debug("Received header: %s" % header)
    return response
