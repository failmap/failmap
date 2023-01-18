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
import random
import socket
from datetime import datetime, timedelta
from ipaddress import AddressValueError
from typing import Dict, List, Optional, Union, Tuple

import pytz
import requests
import urllib3
from celery import Task, group
from django.conf import settings
from requests import HTTPError
from requests.exceptions import ChunkedEncodingError, ContentDecodingError, SSLError

from websecmap.celery import app, EXPIRES_IN_ONE_DAY
from websecmap.organizations.models import Url
from websecmap.scanners import init_dict, plannedscan
from websecmap.scanners.models import Endpoint, UrlIp
from websecmap.scanners.plannedscan import retrieve_endpoints_from_urls
from websecmap.scanners.scanner.__init__ import (
    allowed_to_discover_endpoints,
    unique_and_random,
)
from websecmap.scanners.scanner.filter import (
    generic_plan_scan,
    filter_endpoints_only,
    merge_endpoints_filter,
    apply_organzation_or_endpoint_filter_before_url_filter,
    merge_urls_filter,
)
from websecmap.scanners.scanner.utils import CELERY_IP_VERSION_QUEUE_NAMES
from requests_toolbelt.adapters import host_header_ssl

# suppress InsecureRequestWarning, we do those request on purpose.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger(__package__)

# don't contact http/443 and https/80. You can, but that is 99.99 waste data.
STANDARD_HTTP_PORTS = [80, 8008, 8080]
STANDARD_HTTPS_PORTS = [443, 8443]

# make sure ALL the ports in preferred port order map to a protocol
PORT_TO_PROTOCOL = {80: "http", 8008: "http", 8080: "http", 443: "https", 8443: "https"}

PREFERRED_PORT_ORDER = [443, 80, 8443, 8080, 8008]

CONTENT_FOUND_WITH_ENCODING_ISSUES = "content_found_with_encoding_issues"
NO_CONTENT_BUT_ERROR_INDICATES_SERVER = "no_content_but_error_indicates_server"
NO_CONTENT_AND_SERVER_INDICATES_ERROR = "no_content_and_server_indicates_error"
GENERIC_EXCEPTION = "generic_exception"
FOUND_WITH_IP = "found_with_ip"
NO_HTTP_STATUS_CODE = "no_http_status_code"
FOUND_WITH_HOSTNAME = "found_with_hostname"

"""
http://2.python-requests.org/en/master/user/advanced/?highlight=timeout%3D#timeouts

The connect timeout is the number of seconds Requests will wait for your client to establish a connection to a
remote machine (corresponding to the connect()) call on the socket. It’s a good practice to set connect timeouts
to slightly larger than a multiple of 3, which is the default TCP packet retransmission window.

1 second is surely too short, it results in a lot of false positives, especially when scanning a lot of sites.
Make it very long, like 20 seconds, to make sure not too much stuff gets rediscovered
"""
CONNECT_TIMEOUT = 5

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


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def plan_discover(**kwargs):
    kwargs = merge_urls_filter(STANDARD_URL_FILTER, **kwargs)
    generic_plan_scan(SCANNER_NAME, "discover", apply_organzation_or_endpoint_filter_before_url_filter, **kwargs)


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def plan_verify(**kwargs):
    kwargs = merge_endpoints_filter(STANDARD_ENDPOINT_FILTER, **kwargs)
    generic_plan_scan(SCANNER_NAME, "verify", filter_endpoints_only, **kwargs)


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
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


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
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


@app.task(queue="4and6", expires=EXPIRES_IN_ONE_DAY)
def get_ips(url: str):
    ipv4 = get_ipv4(url) if settings.NETWORK_SUPPORTS_IPV4 else ""
    ipv6 = get_ipv6(url) if settings.NETWORK_SUPPORTS_IPV6 else ""
    return ipv4, ipv6


# It's possible you don't get an address back, it could not be configured on our or their side.
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
    connection_result: bool = False, exception: Optional[Union[Exception, str]] = None
) -> Dict[str, str]:
    data = {"result": connection_result, "error": ""}

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
ACCEPTABLE_CONNECTION_ERRORS = [
    "BadStatusLine",
    "CertificateError",
    "certificate verify failed",
    "bad handshake",
    # Handshake failure: so there is an option to create a handshake, but perhaps the server wont respond.
    # Still a valid endpoint.
    "SSLV3_ALERT_HANDSHAKE_FAILURE",
    # When connecting based on ip address and separate host header, the error returned
    # might not be an SSLV3_ALERT_HANDSHAKE_FAILURE but an TLSV1_ALERT_INTERNAL_ERROR.
    # In that case there is still a connection, although there is something going wrong with TLS.
    # in general all SSLErrors mean there is a connection.
    "TLSV1_ALERT_INTERNAL_ERROR",
    # Done: what to do with a connection reset. It denotes that there is a service running
    #  because otherwise there would not be a RST from the TCP handshake. It frequently happens
    #  that a http site redirects to https and the https gives a connection reset.
    #  In this case we follow what nmap does; it means the port is open. So perhaps this method
    #  should be called 'has open port' or 'runs a service'. While we can't connect there is
    #  definitely a service running there, which means scans should take place.
    #  -> this will move 'missing https' endpoint warnings to 'could not test' errors.
    "Connection aborted",
]


@app.task(queue="4and6", expires=EXPIRES_IN_ONE_DAY)
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
        NO_CONTENT_BUT_ERROR_INDICATES_SERVER,
        FOUND_WITH_HOSTNAME,
        FOUND_WITH_IP,
        NO_HTTP_STATUS_CODE,
    ]

    uri = build_uri_from_components(protocol, url, port, ip_version)
    if not uri:
        return connection_answer(False, f"ipv{ip_version}_resolve_error")

    log.debug("Attempting connect via ip on: %s", uri)
    answer, message = http_call_handling_exceptions(request_via_ip, **{"uri": uri, "url": url})
    log.debug(f"- Answer: {answer}, exc: {message}")
    if message in ok_answers:
        return connection_answer(True, message)

    # instead of trying on no_content_and_server_indicates_error, always retry this way
    # why? because there might be timeouts via approach 1 that don't occur via approach 2.
    log.debug("Attempting connect via name on: %s:", url)
    answer, message = http_call_handling_exceptions(
        request_via_hostname, **{"protocol": protocol, "url": url, "port": port}
    )
    log.debug(f"- Answer: {answer}, exc: {message}")
    if message in ok_answers:
        return connection_answer(True, message)

    log.debug("No http connection possible")
    return connection_answer(False, message)


def http_call_handling_exceptions(callable, **args) -> Tuple[str, str]:
    try:
        log.debug(f"Calling {callable.__name__} with args: {args}")
        answer = callable(**args)
        return answer["result"], answer["error"]
    except (ChunkedEncodingError, ContentDecodingError) as my_exception:
        log.debug(f"- Exception: {my_exception}")
        # There is a connection and you can get something back. But it doesn't decode properly.
        # For example InvalidChunkLength(got length b'<!DOCTYPE html>\\n', 0 bytes read)",
        return CONTENT_FOUND_WITH_ENCODING_ISSUES, str(my_exception)
    except (ConnectionError, HTTPError, SSLError, requests.RequestException) as my_exception:
        log.debug(f"- Exception: {my_exception}")
        if has_acceptable_error(str(my_exception.args)):
            return NO_CONTENT_BUT_ERROR_INDICATES_SERVER, str(my_exception)

        # this has to be retried using get_via_hostname.
        return NO_CONTENT_AND_SERVER_INDICATES_ERROR, str(my_exception)
    # Whatever timeouts and other junk that might play up...
    except BaseException as my_exception:  # pylint: disable=broad-except
        log.debug(f"- Exception: {my_exception}")
        return GENERIC_EXCEPTION, str(my_exception)


def request_via_ip(uri, url) -> Dict[str, str]:
    # https://stackoverflow.com/questions/43156023/what-is-http-host-header#43156094
    s = requests.Session()
    s.mount("https://", host_header_ssl.HostHeaderSSLAdapter())
    # Use HEAD request to only fetch headers which improves performance.
    # Some servers (eg: https://gvo.schiedam.nl/) cause a read timeout when
    # using GET request as the connection is waiting on more data after the
    # body is transmitted. There is no clue yet to why. Using HEAD also mitigates
    # this issues.
    response = s.head(
        uri,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        allow_redirects=False,  # redirect = connection
        verify=False,  # nosec any tls = connection
        headers=create_standard_request_headers(url),
    )

    log.debug("Response: %s", response)

    if response.status_code:
        return connection_answer(True, FOUND_WITH_IP)
    return connection_answer(True, NO_HTTP_STATUS_CODE)


def request_via_hostname(protocol, url, port) -> Dict[str, str]:
    # No acceptable answer? Try a normal connection:
    # This might be due to the fact that a firewall is blocking direct requests to the IP with a different
    # host. Seen this in edienstenburgerzaken.purmerend.nl, which is annoying. So we're going to try
    # to connect again, but then with the normal host, without IP. Note that this requires that the
    # correct queue is used to connect to the network. This might not work on your development machine
    # as it might connect over the wrong network
    # Basically perform the same checks on the url directly, with a more extensive request that can be debugged
    full_url = f"{protocol}://{url}:{port}"
    response = requests.head(
        full_url,
        headers=create_standard_request_headers(url),
        verify=False,
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        allow_redirects=False,
    )

    log.debug("Response: %s", response)

    if response.status_code:
        return connection_answer(True, FOUND_WITH_HOSTNAME)
    return connection_answer(True, NO_HTTP_STATUS_CODE)


def build_uri_from_components(protocol: str, url: str, port: int, ip_version: int) -> Optional[str]:
    if ip_version == 4:
        ip_address = get_ipv4(url)
        return f"{protocol}://{ip_address}:{port}" if ip_address else None
    else:
        ip_address = get_ipv6(url)
        # note the brackets in ipv6 addresses!
        return f"{protocol}://[{ip_address}]:{port}" if ip_address else None


def create_standard_request_headers(url: str) -> Dict[str, str]:
    return {
        "Host": url,
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


def has_acceptable_error(strerror: str) -> bool:
    log.debug(strerror)
    acceptable = any(True for error in ACCEPTABLE_CONNECTION_ERRORS if error in strerror)
    if acceptable:
        log.debug("Acceptable error. There is a server, but could not communicate directly: %s", strerror)
    return acceptable


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
def connect_result(result: Dict[str, str], protocol: str, url_id: int, port: int, ip_version: int, origin: str = ""):
    if result["result"]:
        save_endpoint(protocol, url_id, port, ip_version, f"ok/{origin}/{result['error']}")
    else:
        kill_endpoint(protocol, url_id, port, ip_version, f"error/{origin}/{result['error']}")
    return True


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
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


def save_endpoint(protocol: str, url_id: int, port: int, ip_version: int, origin: str = ""):
    log.debug(
        "Endpoint save attempt: protocol: %s, url_id: %s, port: %s, ip_version: %s, origin: %s.",
        protocol,
        url_id,
        port,
        ip_version,
        origin,
    )

    # prevent duplication
    if endpoint_exists(url_id, port, protocol, ip_version):
        log.debug("Endpoint is already in the database")
        return

    similar = get_similar_dead_endpoint_in_last_n_days(url_id, port, protocol, ip_version, days=60)
    if similar:
        log.debug("Reviving similar endpoint")
        return revive_similar_endpoint(similar, origin)

    log.debug("Saving new endpoint")
    endpoint = Endpoint()
    endpoint.url = Url.objects.all().filter(id=url_id).first()

    endpoint.port = port
    endpoint.protocol = protocol
    endpoint.ip_version = ip_version

    endpoint.is_dead = False
    endpoint.discovered_on = datetime.now(pytz.utc)
    # endpoint.dossier = "Found using the http scanner."  #
    # no other place to put it:
    endpoint.is_dead_reason = origin[:255]
    endpoint.save()
    log.info("Added endpoint added to database: %s", endpoint)


def revive_similar_endpoint(similar, origin):
    log.debug("Similar endpoint found that died in the last 30 days, reviving: %s", similar)
    similar.is_dead = False
    similar.is_dead_since = None
    similar.is_dead_reason += "Revived."
    similar.is_dead_reason = origin[:255]
    similar.save()
    return


@app.task(queue="storage", expires=EXPIRES_IN_ONE_DAY)
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
    url.not_resolvable_since = datetime.now(pytz.utc)
    url.not_resolvable_reason = "No IPv4 or IPv6 address found in http scanner."
    url.save()

    Endpoint.objects.all().filter(url=url).update(
        is_dead=True, is_dead_since=datetime.now(pytz.utc), is_dead_reason="Url was killed"
    )

    UrlIp.objects.all().filter(url=url).update(
        is_unused=True, is_unused_since=datetime.now(pytz.utc), is_unused_reason="Url was killed"
    )


def endpoint_exists(url_id: int, port: int, protocol: str, ip_version: int) -> int:
    return (
        Endpoint.objects.all()
        .filter(url=url_id, port=port, ip_version=ip_version, protocol=protocol, is_dead=False)
        .count()
    )


def get_similar_dead_endpoint_in_last_n_days(
    url_id: int, port: int, protocol: str, ip_version: int, days: int = 30
) -> Endpoint:
    days_ago = datetime.now(pytz.utc) - timedelta(days=days)
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
        endpoint.is_dead_since = datetime.now(pytz.utc)
        endpoint.is_dead_reason = f"Not found in HTTP Scanner anymore ({origin})."[:255]
        endpoint.save()


@app.task(queue="4and6")
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


def redirects_to_safety(url: str):
    """
    Also includes the ip-version of the endpoint. Implies that the endpoint resolves.
    Any safety over any network is accepted now, both A and AAAA records.

    To enable debugging: logging.basicConfig(level=logging.DEBUG)

    :param endpoint:
    :return:
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
        return False
    except (Exception) as my_exception:  # noqa  # pylint: disable=broad-except
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
        return False


def _follow_history_up_until_safety(response):
    log.debug("Request was redirected, there is hope. Redirect path:")
    for index, resp in enumerate(response.history):
        log.debug("- Redirect %s: %s.", index, resp.url)
    log.debug("Final destination:")
    log.debug("%s: %s", response.status_code, response.url)

    if response.url.startswith("https://"):
        log.debug("Url starts with https, so it redirects to safety.")
        return True
    log.debug("Url is not redirecting to a safe url.")
    return False


# http://useragentstring.com/pages/useragentstring.php/
def get_random_user_agent():
    user_agents = [
        # Samsung Galaxy S6
        "Mozilla/5.0 (Linux; Android 6.0.1; SM-G920V Build/MMB29K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/52.0.2743.98 Mobile Safari/537.36",
        # HTC One M9
        "Mozilla/5.0 (Linux; Android 6.0; HTC One M9 Build/MRA58K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/52.0.2743.98 Mobile Safari/537.36",
        # Windows 10 with Edge
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36 Edge/12.246",
        # Safari
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/601.3.9 "
        "(KHTML, like Gecko) Version/9.0.2 Safari/601.3.9",
        # Windows 7
        "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/47.0.2526.111 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:64.0) Gecko/20100101 Firefox/64.0",
    ]

    return random.choice(user_agents)
