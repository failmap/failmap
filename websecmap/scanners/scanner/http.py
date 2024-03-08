"""
Scans for HTTP sites.

If there is a HTTP site on port 80, but there is not a TLS equivalent: give points.
Every http site that does want to instantly upgrade gets 10 points? (how to determine?)

Manages endpoints for port http/80.

Perhaps makes endpoint management more generic.

This also helps with making more screenshots with the browser.

TLS result might be flaky depending on the used TLS lib on the server:
https://stackoverflow.com/questions/26733462/ssl-and-tls-in-python-requests#26734133
https://stackoverflow.com/questions/45290943/how-to-force-timeout-on-pythons-request-librar
y-including-dns-lookup

https://en.wikipedia.org/wiki/List_of_TCP_and_UDP_port_numbers
HTTPS: 443, 832, 981, 1311, 7000, 7002, 8243, 8333, 8531, 8888, 9443, 12043, 12443, 18091, 18092
Likely: 443, 8443

HTTP: 80, 280, 591, 593, 2480, 4444, 4445, 4567, 5000, 5104, 5800, 5988, 7001, 8008, 8042, 8080,
      8088, 8222, 8280, 8281, 8530, 8887, 8888, 9080, 9981, 11371, 12046, 19080,
Likely: 80, 8080, 8008, 8888, 8088

"""
import ipaddress
import logging
import socket
import tldextract
from datetime import datetime, timedelta, timezone
from ipaddress import AddressValueError
from typing import Dict, List, Optional, Tuple, Union

import requests
import urllib3
from celery import Task, group
from django.conf import settings
from requests import HTTPError
from requests.exceptions import ChunkedEncodingError, ContentDecodingError, SSLError
from requests_toolbelt.adapters import host_header_ssl

from websecmap.app.constance import constance_cached_value
from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners import init_dict, plannedscan
from websecmap.scanners.models import Endpoint, UrlIp
from websecmap.scanners.plannedscan import retrieve_endpoints_from_urls
from websecmap.scanners.scanner.__init__ import allowed_to_discover_endpoints, unique_and_random
from websecmap.scanners.scanner.filter import (
    apply_organzation_or_endpoint_filter_before_url_filter,
    filter_endpoints_only,
    generic_plan_scan,
    merge_endpoints_filter,
    merge_urls_filter,
)
from websecmap.scanners.scanner.utils import CELERY_IP_VERSION_QUEUE_NAMES

# suppress InsecureRequestWarning, we do those request on purpose.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger(__package__)

# don't contact http/443 and https/80. You can, but that is 99.99 waste data.
STANDARD_HTTP_PORTS = [80, 8008, 8080]
STANDARD_HTTPS_PORTS = [443, 8443]

# make sure ALL the ports in preferred port order map to a protocol
# running tls over non standard ports makes more sense...
PORT_TO_PROTOCOL = {80: "http", 8008: "http", 8080: "http", 443: "https", 8443: "https"}

PREFERRED_PORT_ORDER = [443, 80, 8443, 8080, 8008]

CONTENT_FOUND_WITH_ENCODING_ISSUES = "content_found_with_encoding_issues"
CONTENT_FOUND_WITH_SSL_ERRORS = "content_found_with_ssl_errors"
NO_CONTENT_BUT_ERROR_INDICATES_SERVER = "no_content_but_error_indicates_server"
NO_CONTENT_AND_SERVER_INDICATES_ERROR = "no_content_and_server_indicates_error"
GENERIC_EXCEPTION = "generic_exception"
FOUND_WITH_IP = "found_with_ip"
NO_HTTP_STATUS_CODE = "no_http_status_code"
FOUND_WITH_HOSTNAME = "found_with_hostname"

# if an endpoint dies and it is rediscovered, it will be revived instead of making a new one.
ENDPOINT_REVIVAL_PERIOD_DAYS = 90

"""
http://2.python-requests.org/en/master/user/advanced/?highlight=timeout%3D#timeouts

The connect timeout is the number of seconds Requests will wait for your client to establish a connection to a
remote machine (corresponding to the connect()) call on the socket. It’s a good practice to set connect timeouts
to slightly larger than a multiple of 3, which is the default TCP packet retransmission window.

1 second is surely too short, it results in a lot of false positives, especially when scanning a lot of sites.
Make it very long, like 20 seconds, to make sure not too much stuff gets rediscovered
"""
CONNECT_TIMEOUT = 15

"""
Once your client has connected to the server and sent the HTTP request, the read timeout is the number of seconds the
client will wait for the server to send a response. (Specifically, it’s the number of seconds that the client will wait
between bytes sent from the server. In 99.9% of cases, this is the time before the server sends the first byte).
7 seconds is way too short, make it 30 so the server has all the time in the world to respond. Otherwise too much
of the same stuff is re-discovered.
"""
READ_TIMEOUT = 15

SCANNER_NAME = "http"
STANDARD_ENDPOINT_FILTER = {"protocol__in": ["https", "http"], "is_dead": False}
STANDARD_URL_FILTER = {"is_dead": False}


@app.task(queue="kickoff", ignore_result=True)
def plan_discover(**kwargs):
    kwargs = merge_urls_filter(STANDARD_URL_FILTER, **kwargs)
    generic_plan_scan(SCANNER_NAME, "discover", apply_organzation_or_endpoint_filter_before_url_filter, **kwargs)


@app.task(queue="kickoff", ignore_result=True)
def plan_verify(**kwargs):
    kwargs = merge_endpoints_filter(STANDARD_ENDPOINT_FILTER, **kwargs)
    generic_plan_scan(SCANNER_NAME, "verify", filter_endpoints_only, **kwargs)


@app.task(queue="kickoff")
def compose_planned_discover_task(**kwargs):
    urls = plannedscan.pickup(activity="discover", scanner="http", amount=kwargs.get("amount", 25))
    return compose_discover_task(urls)


def compose_manual_discover_task(organizations_filter: dict = None, urls_filter: dict = None, **kwargs) -> Task:
    organizations_filter, urls_filter = init_dict(organizations_filter, urls_filter)
    """Discovers HTTP/HTTPS endpoints by attempting to connect to them.

    *This is an implementation of `compose_discover_task`.
    For more documentation about this concept, arguments and concrete
    examples of usage refer to `compose_discover_task` in `types.py`.*
    """

    if not allowed_to_discover_endpoints("http"):
        return group()

    kwargs = merge_urls_filter(STANDARD_URL_FILTER, urls_filter=urls_filter)
    urls = apply_organzation_or_endpoint_filter_before_url_filter(**kwargs)
    return compose_discover_task(urls)


def compose_discover_task(urls: List[Url]):
    tasks = []

    for ip_version in [4, 6]:
        for port in PREFERRED_PORT_ORDER:
            for url in urls:
                tasks.append(
                    can_connect.si(protocol=PORT_TO_PROTOCOL[port], url=url.url, port=port, ip_version=ip_version).set(
                        queue=CELERY_IP_VERSION_QUEUE_NAMES[ip_version]
                    )
                    | connect_result.s(
                        protocol=PORT_TO_PROTOCOL[port],
                        url_id=url.pk,
                        port=port,
                        ip_version=ip_version,
                        origin="http_discover",
                    )
                    | plannedscan.finish.si("discover", "http", url.pk)
                )

    return group(tasks)


@app.task(queue="kickoff")
def compose_planned_verify_task(**kwargs):
    urls = plannedscan.pickup(activity="verify", scanner="http", amount=kwargs.get("amount", 25))
    return compose_verify_task(urls)


def compose_manual_verify_task(
    organizations_filter: dict = None, urls_filter: dict = None, endpoints_filter: dict = None, **kwargs
) -> Task:
    """Verifies existing https and http endpoints. Is pretty quick, as it will not stumble upon non-existing services
    as much.
    """

    if not allowed_to_discover_endpoints("http"):
        return group()

    kwargs = merge_endpoints_filter(STANDARD_ENDPOINT_FILTER, **kwargs)
    urls = filter_endpoints_only(**kwargs)
    return compose_verify_task(urls)


def compose_verify_task(urls):
    endpoints, urls_without_endpoints = retrieve_endpoints_from_urls(urls, protocols=["http", "https"])
    endpoints = unique_and_random(endpoints)

    # remove urls that don't have the relevant endpoints anymore
    for url_id in urls_without_endpoints:
        plannedscan.finish("verify", "http", url_id)

    tasks = group(
        can_connect.si(
            protocol=endpoint.protocol, url=endpoint.url.url, port=endpoint.port, ip_version=endpoint.ip_version
        ).set(queue=CELERY_IP_VERSION_QUEUE_NAMES[endpoint.ip_version])
        | connect_result.s(
            protocol=endpoint.protocol,
            url_id=endpoint.url.pk,
            port=endpoint.port,
            ip_version=endpoint.ip_version,
            origin="http_verify",
        )
        | plannedscan.finish.si("verify", "http", endpoint.url.pk)
        for endpoint in endpoints
    )

    log.info("Verifying %s http/https endpoints.", len(endpoints))

    return tasks


@app.task(queue="internet")
def get_ips(url: str):
    ipv4 = get_ipv4(url) if settings.NETWORK_SUPPORTS_IPV4 else ""
    ipv6 = get_ipv6(url) if settings.NETWORK_SUPPORTS_IPV6 else ""
    return ipv4, ipv6


# It's possible you don't get an address back, it could not be configured on our or their side.
@app.task(queue="internet")
def get_ipv4(url: str):
    # https://www.iana.org/assignments/iana-ipv4-special-registry/iana-ipv4-special-registry.xhtml
    ipv4 = ""

    try:
        ipv4 = socket.gethostbyname(url)
        log.debug("%s has IPv4 address: %s", url, ipv4)
    except Exception as ex:  # pylint: disable=broad-except
        # when not known: [Errno 8] nodename nor servname provided, or not known
        log.debug("Get IPv4 error on %s: %s", url, ex)

    # the contents of the DNS record can be utter garbage, there is absolutely no guarantee that this is an IP
    # it could be an entire novel, or images
    try:
        if ipv4:
            address = ipaddress.IPv4Address(ipv4)
            if not address.is_global:
                ipv4 = ""
    except (AddressValueError, ValueError):
        log.debug("IPv4 address was not recognized on %s: %s", url, ipv4)
        ipv4 = ""

    return ipv4


# It's possible you don't get an address back, it could not be configured on our or their side.
@app.task(queue="internet")
def get_ipv6(url: str):
    # https://www.iana.org/assignments/iana-ipv6-special-registry/iana-ipv6-special-registry.xhtml
    ipv6 = ""

    try:
        # dig AAAA faalkaart.nl +short (might be used for debugging)
        my_socket = socket.getaddrinfo(url, None, socket.AF_INET6)
        ipv6 = my_socket[0][4][0]

        # six to four addresses make no sense
        if str(ipv6).startswith("::ffff:"):
            log.debug(
                "Six-to-Four address %s discovered on %s, did you configure IPv6 connectivity correctly? "
                "Removing this IPv6 address from result to prevent database pollution.",
                ipv6,
                url,
            )
            ipv6 = ""
        else:
            log.debug("%s has IPv6 address: %s", url, ipv6)
    except Exception as ex:  # pylint: disable=broad-except
        # when not known: [Errno 8nodename nor servname provided, or not known
        log.debug("Get IPv6 error on %s: %s", url, ex)

    try:
        if ipv6:
            address = ipaddress.IPv6Address(ipv6)
            if not address.is_global:
                ipv6 = ""
    except (AddressValueError, ValueError):
        log.debug("IPv6 address was not recognized on %s: %s", url, ipv6)
        ipv6 = ""

    return ipv6


"""
    When doing a lot of connections, try to do them in semi-random order also not to overload networks/firewalls

    Don't try and overload the network with too many connections.
    The (virtual) network (card) might have a problem keeping up.
    Firewalls might see it as hostile.
    Our database might be overloaded with work,

    To consider the rate limit:
    There are about 11000 endpoints at this moment.
    3/s = 180/m = 1800/10m = 10800/h
    4/s = 240/m = 2400/10m = 14400/h
    5/s = 300/m = 3000/10m = 18000/h
    10/s = 600/m = 6000/10m = 36000/h

    given many won't exist and time out, it's fine to set it to 20...

    on the development machine it scans all within 10 minutes. About 20/s.
"""


def connection_answer(
    connection_result: bool = False, exception: Optional[Union[Exception, str]] = None, response_text: str = ""
) -> Dict[str, str]:
    data = {"result": connection_result, "error": "", "response_text": response_text}

    if not exception:
        return data

    # There can still be an error even when a connection was possible. For example a TLS error, but that indicates
    # there was a connection possible still.
    if isinstance(exception, Exception):
        data["error"] = type(exception).__name__
    else:
        data["error"] = exception

    return data


# These errors indicate there _IS_ a connection, but there is some kind of misconfiguration.
# These are snippets from the received errors
# all lowercase!
ACCEPTABLE_CONNECTION_ERRORS = [
    "badstatusline",
    "certificateerror",
    "certificate verify failed",
    "bad handshake",
    # handshake failure: so there is an option to create a handshake, but perhaps the server wont respond.
    # still a valid endpoint.
    "sslv3_alert_handshake_failure",
    # when connecting based on ip address and separate host header, the error returned
    # might not be an sslv3_alert_handshake_failure but an tlsv1_alert_internal_error.
    # in that case there is still a connection, although there is something going wrong with tls.
    # in general all sslerrors mean there is a connection.
    "tlsv1_alert_internal_error",
    # done: what to do with a connection reset. it denotes that there is a service running
    #  because otherwise there would not be a rst from the tcp handshake. it frequently happens
    #  that a http site redirects to https and the https gives a connection reset.
    #  in this case we follow what nmap does; it means the port is open. so perhaps this method
    #  should be called 'has open port' or 'runs a service'. while we can't connect there is
    #  definitely a service running there, which means scans should take place.
    #  -> this will move 'missing https' endpoint warnings to 'could not test' errors.
    "connection aborted",
    "tlsv13_alert_certificate_required",
    "unexpected_eof_while_reading",
    "tlsv1_unrecognized_name",
    "wrong_version_number",
    "eof occurred in violation of protocol (_ssl.c:1007)",
    "unsafe_legacy_renegotiation_disabled",
    "sslv3_alert_bad_certificate",
    "unsupported_protocol",
    "decryption_failed_or_bad_record_mac",
    "sslv3_alert_certificate_unknown",
    "dh_key_too_small",
    "sslv3_alert_illegal_parameter",
]


@app.task(queue="internet")
def can_connect(protocol: str, url: str, port: int, ip_version: int) -> Dict[str, str]:
    """
    Searches for both IPv4 and IPv6 IP addresses / types.

    The algorithm is very simple: if there is a http status code, or "a response" there is an
    http(s) server. Some servers don't return a status code, others have problems with tls.

    It's possible to have a TLS site on port 80 and a non-TLS site on port 443.

    As long as there is a "sort of" response we just assume there is a website there.
    """

    ok_answers = [
        CONTENT_FOUND_WITH_ENCODING_ISSUES,
        CONTENT_FOUND_WITH_SSL_ERRORS,
        NO_CONTENT_BUT_ERROR_INDICATES_SERVER,
        FOUND_WITH_HOSTNAME,
        FOUND_WITH_IP,
        NO_HTTP_STATUS_CODE,
    ]

    uri = build_uri_from_components(protocol, url, port, ip_version)
    if not uri:
        return connection_answer(False, f"ipv{ip_version}_resolve_error", "")

    log.debug("Attempting connect via ip on: %s", uri)
    answer, message, response_text = http_call_handling_exceptions(request_via_ip, **{"uri": uri, "url": url})
    log.debug(f"- Answer: {answer}, exc: {message}")
    if answer in ok_answers or message in ok_answers:
        log.debug("Got an ok answer, so we can connect, but not easily...")
        return connection_answer(True, message, response_text)

    # instead of trying on no_content_and_server_indicates_error, always retry this way
    # why? because there might be timeouts via approach 1 that don't occur via approach 2.
    log.debug("Attempting connect via name on: %s:", url)
    answer, message, response_text = http_call_handling_exceptions(
        request_via_hostname, **{"protocol": protocol, "url": url, "port": port}
    )
    log.debug(f"- Answer: {answer}, exc: {message}")
    if answer in ok_answers or message in ok_answers:
        return connection_answer(True, message, response_text)

    log.debug("No http connection possible")
    return connection_answer(False, message, response_text)


def http_call_handling_exceptions(callable, **args) -> Tuple[str, str, str]:
    # returns message and detail info
    try:
        log.debug(f"Calling {callable.__name__} with args: {args}")
        answer = callable(**args)
        return answer["result"], answer["error"], answer["response_text"]
    except (ChunkedEncodingError, ContentDecodingError) as my_exception:
        log.debug(f"- Exception: {my_exception}")
        # There is a connection and you can get something back. But it doesn't decode properly.
        # For example InvalidChunkLength(got length b'<!DOCTYPE html>\\n', 0 bytes read)",
        return CONTENT_FOUND_WITH_ENCODING_ISSUES, str(my_exception), ""
    except SSLError as my_exception:
        # SSl issues are ok, this means there is something to connect to, but it doesn't matter if we can't connect
        log.debug(f"- Exception: {my_exception}")
        return CONTENT_FOUND_WITH_SSL_ERRORS, str(my_exception), ""
    except (ConnectionError, HTTPError, requests.RequestException) as my_exception:
        log.debug(f"- Exception: {my_exception}")
        if has_acceptable_error(str(my_exception)):
            return NO_CONTENT_BUT_ERROR_INDICATES_SERVER, str(my_exception), ""

        # this has to be retried using get_via_hostname.
        return NO_CONTENT_AND_SERVER_INDICATES_ERROR, str(my_exception), ""
    # Whatever timeouts and other junk that might play up...
    except BaseException as my_exception:  # pylint: disable=broad-except
        log.debug(f"- Exception: {my_exception}")
        return GENERIC_EXCEPTION, str(my_exception), ""


def request_via_ip(uri, url) -> Dict[str, str]:
    # https://stackoverflow.com/questions/43156023/what-is-http-host-header#43156094
    s = requests.Session()
    s.mount("https://", host_header_ssl.HostHeaderSSLAdapter())
    # Use HEAD request to only fetch headers which improves performance.
    # Some servers (eg: https://gvo.schiedam.nl/) cause a read timeout when
    # using GET request as the connection is waiting on more data after the
    # body is transmitted. There is no clue yet to why. Using HEAD also mitigates
    # this issues.
    response = s.get(
        uri,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        allow_redirects=False,  # redirect = connection
        verify=False,  # nosec any tls = connection
        stream=True,  # don't read the message body unless it is required
        # no redirect, so setting the host is ok
        headers=create_standard_request_headers(url),
    )

    log.debug("Response: %s", response)
    response_text = f"{response.status_code}: {response.text[:100]}"

    if response.status_code:
        return connection_answer(connection_result=True, exception=FOUND_WITH_IP, response_text=response_text)
    return connection_answer(connection_result=True, exception=NO_HTTP_STATUS_CODE, response_text=response_text)


def request_via_hostname(protocol, url, port) -> Dict[str, str]:
    # No acceptable answer? Try a normal connection:
    # This might be due to the fact that a firewall is blocking direct requests to the IP with a different
    # host. Seen this in edienstenburgerzaken.purmerend.nl, which is annoying. So we're going to try
    # to connect again, but then with the normal host, without IP. Note that this requires that the
    # correct queue is used to connect to the network. This might not work on your development machine
    # as it might connect over the wrong network
    # Basically perform the same checks on the url directly, with a more extensive request that can be debugged
    full_url = f"{protocol}://{url}:{port}"
    response = requests.get(
        full_url,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        allow_redirects=False,
        verify=False,
        stream=True,  # don't read the message body unless it is required
        # no redirect, so setting the host is ok
        headers=create_standard_request_headers(url),
    )

    log.debug("Response: %s", response)
    response_text = f"{response.status_code}: {response.text[:100]}"

    if response.status_code:
        return connection_answer(connection_result=True, exception=FOUND_WITH_HOSTNAME, response_text=response_text)
    return connection_answer(connection_result=True, exception=NO_HTTP_STATUS_CODE, response_text=response_text)


def build_uri_from_components(protocol: str, url: str, port: int, ip_version: int) -> Optional[str]:
    if ip_version == 4:
        ip_address = get_ipv4(url)
        return f"{protocol}://{ip_address}:{port}" if ip_address else None
    else:
        ip_address = get_ipv6(url)
        # note the brackets in ipv6 addresses!
        return f"{protocol}://[{ip_address}]:{port}" if ip_address else None


def create_standard_request_headers(url: str = "") -> Dict[str, str]:
    data = {
        "User-Agent": get_random_user_agent(),
        # some headers to make this look like a browser request, some domains otherwise just
        # refuse to serve:
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
    }

    # Following redirects with host set will cause issues. The host will be set to the redirect and
    # the receiver will say that it's wrong. So only set the host if there is no redirect.
    if url:
        data["Host"] = url

    return data


def has_acceptable_error(strerror: str) -> bool:
    log.debug(strerror)
    strerror = strerror.lower()
    acceptable = any(True for error in ACCEPTABLE_CONNECTION_ERRORS if error in strerror)
    if acceptable:
        log.debug("Acceptable error. There is a server, but could not communicate directly: %s", strerror)
    return acceptable


@app.task(queue="database")
def connect_result(result: Dict[str, str], protocol: str, url_id: int, port: int, ip_version: int, origin: str = ""):
    if result["result"]:
        save_endpoint(protocol, url_id, port, ip_version, f"ok/{origin}/{result['error']}")
    else:
        kill_endpoint(protocol, url_id, port, ip_version, f"error/{origin}/{result['error']}")
    return True


@app.task(queue="database")
def connect_result_simple(result: bool, protocol: str, url_id: int, port: int, ip_version: int, origin: str = ""):
    # no tracing of what went wrong where, will probably be superseeded with connect_result for tracing purposes
    if result:
        save_endpoint(protocol, url_id, port, ip_version, f"{origin}")
    else:
        kill_endpoint(protocol, url_id, port, ip_version, f"{origin}")
    return True


def resolves(url: str):
    (ip4, ip6) = get_ips(url)
    return bool(ip4 or ip6)


def resolves_on_v4(url: str):
    (ip4, _) = get_ips(url)
    return bool(ip4)


def resolves_on_v6(url: str):
    (_, ip6) = get_ips(url)
    return bool(ip6)


def has_internet_connection(host: str = "8.8.8.8", port: int = 53, connection_timeout: int = 10):
    """
    https://stackoverflow.com/questions/3764291/checking-network-connection#3764660
    Host: 8.8.8.8 (google-public-dns-a.google.com)
    OpenPort: 53/tcp
    Service: domain (DNS/TCP)
    """
    try:
        socket.setdefaulttimeout(connection_timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except Exception as ex:  # pylint: disable=broad-except
        log.debug("No internet connection: %s", ex)
        return False


def force_get_endpoint(protocol: str, url_id: int, port: int, ip_version: int, origin: str = "") -> Endpoint:
    # use a different name for the same function as it is contextually easier to understand.
    return save_endpoint(protocol, url_id, port, ip_version, origin)


def get_endpoint(protocol: str, url_id: int, port: int, ip_version: int, origin: str = "") -> Optional[Endpoint]:
    """Get endpoint, but do not create it if it doesn't exist"""
    return save_endpoint(protocol, url_id, port, ip_version, origin, create=False)


def save_endpoint(protocol: str, url_id: int, port: int, ip_version: int, origin: str = "", create=True) -> Endpoint:
    log.debug(
        "Endpoint save attempt: protocol: %s, url_id: %s, port: %s, ip_version: %s, origin: %s.",
        protocol,
        url_id,
        port,
        ip_version,
        origin,
    )

    # prevent duplication
    if ep := endpoint_exists(url_id, port, protocol, ip_version):
        log.debug("Endpoint is already in the database, returning the existing one.")
        return ep
    else:
        log.error(
            "Endpoint does not exists, url: %s, port: %s, protocol: %s, ip_version: %s",
            url_id,
            port,
            protocol,
            ip_version,
        )
        if not create:
            return None

    if similar := get_similar_dead_endpoint_in_last_n_days(
        url_id, port, protocol, ip_version, days=ENDPOINT_REVIVAL_PERIOD_DAYS
    ):
        log.debug("Reviving similar endpoint, returning that one.")
        return revive_similar_endpoint(similar, origin)

    log.debug("Saving new endpoint")
    endpoint = Endpoint()

    try:
        endpoint.url = Url.objects.all().filter(id=url_id).first()
    except Url.DoesNotExist:
        # do not crash, but make it clear something is wrong
        endpoint.url = ""
        log.error(
            "Could not find url with id, still saving an endpoint with no further connection."
            "Make sure to fix this issue in the source data.",
            extra={
                "url_id": url_id,
                "port": port,
                "protocol": protocol,
                "ip_version": ip_version,
                "origin": origin,
            },
        )

    endpoint.port = port
    endpoint.protocol = protocol
    endpoint.ip_version = ip_version
    endpoint.is_dead = False
    endpoint.discovered_on = datetime.now(timezone.utc)
    endpoint.origin = origin[:255]
    endpoint.save()
    log.info("Added endpoint added to database: %s", endpoint)
    # to trace why endpoints are killed/revived. Does an N+1 on url.url
    log.info("Created endpoint: %s, url: %s. protocol: %s", endpoint, endpoint.url.url, endpoint.protocol)
    return endpoint


def revive_similar_endpoint(similar, origin):
    log.debug("Similar endpoint found that died in the last 30 days, reviving: %s", similar)
    similar.is_dead = False
    similar.is_dead_since = None
    similar.is_dead_reason = f"Revived. {similar.is_dead_reason}"[:255]
    similar.save()
    # to trace why endpoints are killed/revived. Does an N+1 on url.url
    log.info("Revived endpoint: %s, url: %s. protocol: %s", similar, similar.url.url, similar.protocol)
    return similar


@app.task(queue="storage", ignore_result=True)
def kill_url_task(ips, url: Url):
    # only kill if there are no ips.
    if any(ips):
        return

    """
    Sets a URL as not resolvable. Does not touches the is_dead (layer 8) field.

    :param url:
    :return:
    """
    url.not_resolvable = True
    url.not_resolvable_since = datetime.now(timezone.utc)
    url.not_resolvable_reason = "No IPv4 or IPv6 address found in http scanner."
    url.save()

    Endpoint.objects.all().filter(url=url).update(
        is_dead=True, is_dead_since=datetime.now(timezone.utc), is_dead_reason="Url was killed"
    )

    UrlIp.objects.all().filter(url=url).update(
        is_unused=True, is_unused_since=datetime.now(timezone.utc), is_unused_reason="Url was killed"
    )


def endpoint_exists(url_id: int, port: int, protocol: str, ip_version: int) -> Optional[Endpoint]:
    # Log if there are multiple alive endpoints, this is a sign there is a bug somewhere
    endpoints = Endpoint.objects.all().filter(
        url=url_id, port=port, ip_version=ip_version, protocol=protocol, is_dead=False
    )
    if endpoints.count() > 1:
        log.error(
            "Found multiple endpoints with the same data",
            extra={
                "url_id": url_id,
                "port": port,
                "protocol": protocol,
                "ip_version": ip_version,
                "endpoints": endpoints.count(),
            },
        )

    return endpoints.first() if endpoints.count() > 0 else None


def get_similar_dead_endpoint_in_last_n_days(
    url_id: int, port: int, protocol: str, ip_version: int, days: int = 30
) -> Endpoint:
    days_ago = datetime.now(timezone.utc) - timedelta(days=days)
    log.debug(days_ago)
    return (
        Endpoint.objects.all()
        .filter(
            url=url_id, port=port, ip_version=ip_version, protocol=protocol, is_dead=True, is_dead_since__gte=days_ago
        )
        .last()
    )


def kill_endpoint(protocol: str, url_id: int, port: int, ip_version: int, origin: str = ""):
    log.debug(
        "Killing endpoint: protocol: %s, url_id: %s, port: %s, ip_version: %s, origin: %s.",
        protocol,
        url_id,
        port,
        ip_version,
        origin,
    )
    eps = Endpoint.objects.all().filter(url=url_id, port=port, ip_version=ip_version, protocol=protocol, is_dead=False)

    for endpoint in eps:
        endpoint.is_dead = True
        endpoint.is_dead_since = datetime.now(timezone.utc)
        endpoint.is_dead_reason = f"Not found in {protocol} Scanner anymore ({origin})."[:255]
        endpoint.save()

        # to trace why endpoints are killed. Does an N+1 on url.url
        log.info("Killed endpoint: %s, url: %s. protocol: %s", endpoint, endpoint.url.url, endpoint.protocol)


@app.task(queue="internet")
def check_network(code_location=""):
    """
    Used to see if a worker can do IPv6. Will trigger an exception when no ipv4 or ipv6 is available,
    which is logged in sentry and other logs.

    :return:
    """

    log.info("Testing network connection via %s.", code_location)

    log.info("IPv4 is enabled via configuration: %s", settings.NETWORK_SUPPORTS_IPV4)
    log.info("IPv6 is enabled via configuration: %s", settings.NETWORK_SUPPORTS_IPV6)

    # todo: this does not work in all cases, you should run this over the v4 and v6 queues respectively
    can_ipv4 = can_connect("https", "faalkaart.nl", 443, 4)
    can_ipv6 = can_connect("https", "faalkaart.nl", 443, 6)

    if not can_ipv4["result"] or not can_ipv6["result"]:
        raise ConnectionError(
            f"IPv4 enabled in config: {settings.NETWORK_SUPPORTS_IPV4}, "
            f"IPv4 Connection: {can_ipv4['result']}"
            f"IPv4 Error: {can_ipv4['error']}"
            f"IPv6 enabled in config: {settings.NETWORK_SUPPORTS_IPV6}"
            f"IPv6 Connection: 6:{can_ipv6['result']}"
            f"IPv6 Error: {can_ipv6['error']}"
        )

    log.info("Network could be reached could be reached via %s", code_location)


def redirects_to_safety(url: str) -> Tuple[bool, List[Dict[str, str]]]:
    """
    Also includes the ip-version of the endpoint. Implies that the endpoint resolves.
    Any safety over any network is accepted now, both A and AAAA records.

    To enable debugging: logging.basicConfig(level=logging.DEBUG)

    :param url:
    :return: Tuple with the first value true if the last in the chain has https. The second will be filled with
    # the redirects encountered.
    """

    # A feature of requests is to send any headers you've sent when there are redirects.
    # This becomes problematic when you set the Host header. This prevents

    try:
        session = requests.Session()
        response = session.get(
            url,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),  # allow for insane network lag
            allow_redirects=True,  # point is: redirects to safety
            verify=False,  # certificate validity is checked elsewhere, having some https > none
            # redirects do NOT overwrite the host headers. Meaning that following a redirect, the
            # host header is set, which is incorrect. The Host header should only be set in the first
            # request, and should be overwritten by all subsequent requests.
            # The reason we set the host header explicitly, is because we want to contact the webserver
            # via the IP address, so we can explicitly contect IPv4 and IPv6 addresses of this domain.
            # issue was logged here: https://github.com/psf/requests/issues/5196
            headers={
                "User-Agent": get_random_user_agent(),
                # Give some instructions that we want a secure address...
                "Upgrade-Insecure-Requests": "1",
            },
        )

        if response.history:
            return _follow_history_up_until_safety(response)
        log.debug("Request was not redirected, so not going to a safe url.")
        return False, []
    except Exception as my_exception:  # noqa  # pylint: disable=broad-except
        # Replaces basically everything, it's just a plethora of stuff that can go wrong which is outside of our usecase
        # ConnectTimeout,
        # HTTPError,
        # ReadTimeout,
        # Timeout,
        # ConnectionError,
        # SSLError,
        # # It seems that a ConnectionError is still showing up, might be a requests.ConnectionError
        # requests.RequestException
        log.debug("Request resulted into an error, it's not redirecting properly.")
        log.debug("The error retrieved was: %s", my_exception)
        return False, []


def _follow_history_up_until_safety(response) -> Tuple[bool, List[Dict[str, str]]]:
    # we don't need all tracking parameters, just the redirect urls are enough
    redirects = []
    log.debug("Request was redirected, there is hope. Redirect path:")
    for index, resp in enumerate(response.history):
        log.debug("- Redirect %s: %s.", index, resp.url)
        extract = tldextract.extract(resp.url)
        redirects.append({"url": extract.fqdn, "status_code": resp.status_code, "content": resp.text[:100]})
    log.debug("Final destination:")
    log.debug("%s: %s", response.status_code, response.url)
    extract = tldextract.extract(response.url)
    redirects.append({"url": extract.fqdn, "status_code": response.status_code, "content": response.text[:100]})

    if response.url.startswith("https://"):
        log.debug("Url starts with https, so it redirects to safety.")
        return True, redirects
    log.debug("Url is not redirecting to a safe url.")
    return False, redirects


# http://useragentstring.com/pages/useragentstring.php/
def get_random_user_agent() -> str:
    # servers react different to different user-agents, which means that the tests will fluctuate all the time.
    # this has been reduced by returning the same string always.
    # Use a popular browser.
    return constance_cached_value("SCANNER_DEFAULT_BROWSER_USER_AGENT")
