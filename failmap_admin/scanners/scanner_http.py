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
import logging
import socket
from datetime import datetime
from typing import List

import pytz
import requests
from requests import ConnectTimeout, HTTPError, ReadTimeout, Timeout
from requests.exceptions import ConnectionError

from failmap_admin.celery import app
from failmap_admin.scanners.models import Endpoint, UrlIp
from failmap_admin.organizations.models import Url

from .timeout import timeout

logger = logging.getLogger(__package__)


def validate_port(port: int):
    if port > 65535 or port < 0:
        logger.error("Invalid port number, must be between 0 and 65535. %s" % port)
        raise ValueError("Invalid port number, must be between 0 and 65535. %s" % port)


def validate_protocol(protocol: str):
    if protocol not in ["http", "https"]:
        logger.error("Invalid protocol %s, options are: http, https" % protocol)
        raise ValueError("Invalid protocol %s, options are: http, https" % protocol)


def scan_urls_on_standard_ports(urls: List[Url]):
    scan_urls(['http', 'https'], urls, [80, 81, 82, 88, 443, 8008, 8080, 8088, 8443, 8888, 9443])


def scan_urls(protocols: List[str], urls: List[Url], ports: List[int]):

    if not has_internet_connection():
        logger.error("No internet connection! Try again later!")
        return

    for port in ports:
        validate_port(port)

    for protocol in protocols:
        validate_protocol(protocol)

    # put some distance between the times an url is contacted, so it is less pressuring
    # therefore, we do this per port and protocol instead of per url.
    for port in ports:
        for protocol in protocols:
            for url in urls:
                scan_url(protocol, url, port)


def scan_url(protocol: str, url: Url, port: int):
    resolve_task = resolve_and_scan.s(protocol, url, port)
    resolve_task.apply_async()


@app.task
def resolve_and_scan(protocol: str, url: Url, port: int):
    ips = get_ips(url.url)

    # this can take max 20 seconds, no use to wait
    store_task = store_url_ips.s(url, ips)  # administrative, does reverse dns query
    store_task.apply_async()

    if not any(ips):
        kill_url_task = kill_url.s(url)  # administrative
        kill_url_task.apply_async()
        return

    url_revive_task = revive_url.s(url)
    url_revive_task.apply_async()

    # todo: switch between ipv4 and ipv6, make tasks for different workers.
    (ipv4, ipv6) = ips
    if ipv4:
        connect_task = can_connect.s(protocol, url, port, ipv4)  # Network task
        result_task = connect_result.s(protocol, url, port, 4)  # administrative task
        task = (connect_task | result_task)
        task.apply_async()

    if ipv6:
        connect_task = can_connect.s(protocol, url, port, ipv6)  # Network task
        result_task = connect_result.s(protocol, url, port, 6)  # administrative task
        task = (connect_task | result_task)
        task.apply_async()

    # v6 is not yet supported, as we don't have v6 workers yet.


def get_ips(url: str):
    ipv4 = ""
    ipv6 = ""

    try:
        ipv4 = socket.gethostbyname(url)
        logger.debug("%s has IPv4 address: %s" % (url, ipv4))
    except Exception as ex:
        # when not known: [Errno 8] nodename nor servname provided, or not known
        logger.debug("Get IPv4 error: %s" % ex)

    try:
        # dig AAAA faalkaart.nl +short (might be used for debugging)
        x = socket.getaddrinfo(url, None, socket.AF_INET6)
        ipv6 = x[0][4][0]
        logger.debug("%s has IPv6 address: %s" % (url, ipv6))
    except Exception as ex:
        # when not known: [Errno 8nodename nor servname provided, or not known
        logger.debug("Get IPv6 error: %s" % ex)

    return ipv4, ipv6


@app.task
def can_connect(protocol: str, url: Url, port: int, ip: str):
    """
    Searches for both IPv4 and IPv6 IP addresses / types.

    The algorithm is very simple: if there is a http status code, or "a response" there is an
    http(s) server. Some servers don't return a status code, others have problems with tls.
    So you need either build something extremely robust, or make an easy assumption that there
    could be a website there. Given the ports we scan, the probabilty of a website is extremely
    high.

    We don't scan for the obsoleted S-HTTP protocol, only for http and https.

    It's possible to have a TLS site on port 80 and a non-TLS site on port 443. We've seen those.

    This function does not store all ports it couldn't contact. Would we do that, the amount
    of endpoints that are not resolvable explodes. There is not really value in storing the
    non-resolvable urls, as you need to re-scan everything an a while anyway.
    If we would store this, it would be url * ports endpoints. Now it's roughly urls * 1.8.

    TLS does not have to be succesful. We also store https sites where HTTPS completely or
    partially fails. As long as there is a "sort of" response we just assume there is a
    website there. Other TLS scanners can check what's wrong with the connection. Perhaps
    this leads to some false positives or to some other wrong data.
    The big question is: would some https sites only respond IF the right protocol (SSL 1) or
    something like that is spoken to them? Do we need a "special" TLS implementation on our server?

    Todo: futher look if DIG can be of value to us. Until now it seems not so.

    Todo: remove IP from endpoints. (change for version 1.1)

    """
    if ":" in ip:
        uri = "%s://[%s]:%s" % (protocol, ip, port)
    else:
        uri = "%s://%s:%s" % (protocol, ip, port)

    logger.debug("Scanning http(s) server on: %s" % uri)

    try:
        """
        5 seconds network timeout, 8 seconds timeout for server response.
        If we get a redirect, it means there is a server. Don't follow.

        Any status code is enough to verify that there is an endpoint.
        Some servers don't return a status code, that will trigger an exception (AttributeError?)
        
        https://stackoverflow.com/questions/43156023/what-is-http-host-header#43156094
        """
        r = requests.get(uri, timeout=(5, 8), allow_redirects=False, headers={'Host': url.url})
        if r.status_code:
            logger.debug("%s: Host: %s Status: %s" % (uri, url.url, r.status_code))
            return True
        else:
            logger.debug("No status code? Now what?! %s" % url)
            # probably never reached, exception thrown when no status code is present
            return True
    except (ConnectTimeout, Timeout, ReadTimeout) as Ex:
        logger.debug("%s: Timeout! - %s" % (url, Ex))
        return False
    except (ConnectionRefusedError, ConnectionError, HTTPError) as Ex:
        """
        Some errors really mean there is no site. Example is the ConnectionRefusedError: [Errno 61]
        which means the endpoint can be killed.

        There are exceptions that still can be translated into an existing site.
        Until now we've found in responses:
        - BadStatusLine
        - CertificateError
        - certificate verify failed

        Perhaps: (todo)
        - EOF occurred in violation of protocol
        """
        logger.debug("%s: Exception returned: %s" % (url, Ex))
        strerror = Ex.args  # this can be multiple.  # zit in nested exception?
        strerror = str(strerror)  # Cast whatever we get back to a string. Instead of trace.
        if any(["BadStatusLine" in strerror,
                "CertificateError" in strerror,
                "certificate verify failed" in strerror]):
            logger.debug("Exception indicates that there is a server, but we're not able to "
                         "communicate with it correctly. Error: %s" % strerror)
            return True
        else:
            logger.debug("Exception indicates we could not connect to server. Error: %s" % strerror)
            return False


@app.task
def connect_result(result, protocol: str, url: Url, port: int, ip_version: int):
    # logger.info("%s %s" % (url, result))
    # logger.info("%s %s" % (url, url))
    # logger.info("%s %s" % (url, port))
    # logger.info("%s %s" % (url, protocol))
    # logger.info("%s %s" % (url, ip_version))

    if result:
        save_endpoint(protocol, url, port, ip_version)
    else:
        kill_endpoint(protocol, url, port, ip_version)


def resolves(url: str):
    (ip4, ip6) = get_ips(url)
    if ip4 or ip6:
        return True
    return False


def has_internet_connection(host: str="8.8.8.8", port: int=53, connection_timeout: int=10):
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
    except Exception as ex:
        logger.debug("No internet connection: %s" % ex)
        return False


def save_endpoint(protocol: str, url: Url, port: int, ip_version: int):

    # prevent duplication
    if not endpoint_exists(url, port, protocol, ip_version):
        endpoint = Endpoint()
        endpoint.url = url
        endpoint.domain = url.url

        endpoint.port = port
        endpoint.protocol = protocol
        endpoint.ip_version = ip_version

        endpoint.is_dead = False
        endpoint.discovered_on = datetime.now(pytz.utc)
        # endpoint.dossier = "Found using the http scanner."  #
        endpoint.save()
        logger.info("Added endpoint added to database: %s" % endpoint)
    else:
        logger.debug("Endpoint based on parameters was already in database.")

    return


@app.task
def revive_url(url: Url):
    """
    This does not revive all endpoints... There should be new ones to better match with actual
    happenings with servers.

    Should this add a new url instead of reviving the old one to better reflect the network?

    :param url:
    :return:
    """
    if url.not_resolvable:
        url.not_resolvable = False
        url.not_resolvable_since = datetime.now(pytz.utc)
        url.not_resolvable_reason = "Made resolvable again since ip address was found."
        url.save()


@app.task
def kill_url(url: Url):
    url.not_resolvable = True
    url.not_resolvable_since = datetime.now(pytz.utc)
    url.not_resolvable_reason = "No IPv4 or IPv6 address found in http scanner."
    url.save()

    Endpoint.objects.all().filter(url=url).update(is_dead=True,
                                                  is_dead_since=datetime.now(pytz.utc),
                                                  is_dead_reason="Url was killed")

    UrlIp.objects.all().filter(url=url).update(
        is_unused=True,
        is_unused_since=datetime.now(pytz.utc),
        is_unused_reason="Url was killed"
    )


@app.task
def store_url_ips(url: Url, ips):
    """
    Todo: method should be stored in manager

    Be sure to give all ip's that are currently active in one call. Mix IPv4 and IPv6.

    the http endpoint finder will clash with qualys on this method, until we're using the same
    method to discover all ip's this url currently has.
    """

    for ip in ips:

        # sometimes there is no ipv4 or 6 address... or you get some other dirty dataset.
        if not ip:
            continue

        # the same thing that exists already? don't do anything about it.
        if UrlIp.objects.all().filter(url=url, ip=ip, is_unused=False).count():
            continue

        epip = UrlIp()
        epip.ip = ip
        epip.url = url
        epip.is_unused = False
        epip.discovered_on = datetime.now(pytz.utc)
        epip.rdns_name = get_rdns_name(ip)
        epip.save()

    # and then clean up all that are not in the current set of ip's.
    UrlIp.objects.all().filter(url=url, is_unused=False).exclude(ip__in=ips).update(
        is_unused=True,
        is_unused_since=datetime.now(pytz.utc),
        is_unused_reason="cleanup at storing new endpoints"
    )


@timeout(10)
def get_rdns_name(ip):
    reverse_name = ""
    try:
        reverse_name = socket.gethostbyaddr(ip)
    except (TimeoutError, socket.herror):
        # takes too long
        # host doesn't exist
        pass
    except BaseException as e:
        logger.error('Unknown rdns failure %s on ip %s' % (str(e), ip))

    return reverse_name


def endpoint_exists(url, port, protocol, ip_version):
    return Endpoint.objects.all().filter(url=url,
                                         port=port,
                                         ip_version=ip_version,
                                         protocol=protocol,
                                         is_dead=False).count()


def kill_endpoint(protocol: str, url: Url, port: int, ip_version: int):
    eps = Endpoint.objects.all().filter(url=url,
                                        port=port,
                                        ip_version=ip_version,
                                        protocol=protocol,
                                        is_dead=False)

    for ep in eps:
        ep.is_dead = True
        ep.is_dead_since = datetime.now(pytz.utc)
        ep.is_dead_reason = "Not found in HTTP Scanner anymore."
        ep.save()
