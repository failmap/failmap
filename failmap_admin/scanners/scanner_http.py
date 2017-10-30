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

import pytz
import requests
from requests import ConnectTimeout, HTTPError, ReadTimeout, Timeout
from requests.exceptions import ConnectionError

from failmap_admin.celery import app
from failmap_admin.scanners.models import Endpoint

logger = logging.getLogger(__package__)


def validate_port(port):
    if port > 65535 or port < 0:
        logger.error("Invalid port number, must be between 0 and 65535. %s" % port)
        raise ValueError("Invalid port number, must be between 0 and 65535. %s" % port)


def validate_protocol(protocol):
    if protocol not in ["http", "https"]:
        logger.error("Invalid protocol %s, options are: http, https" % protocol)
        raise ValueError("Invalid protocol %s, options are: http, https" % protocol)


def scan_urls_on_standard_ports(urls):
    scan_url(urls, [80, 81, 82, 88, 443, 8008, 8080, 8088, 8443, 8888, 9443], ['http', 'https'])


def scan_urls(urls, ports, protocols):

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
                scan_url(url, port, protocol)


def scan_url(url, port=80, protocol="https"):
    task = scan_url_task.s(url, port, protocol)
    task.apply_async()


@app.task
def scan_url_task(url, port=80, protocol="https"):
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
    domain = "%s://%s:%s" % (protocol, url.url, port)
    logger.debug("Scanning http(s) server on: %s" % domain)

    # the ipv6 address returned here is already compressed.
    (ip4, ip6) = get_ips(url.url)
#
    if not ip4 and not ip6:
        logger.debug("%s: No IPv4 or IPv6 address found. Url not resolvable?" % url)
        url.not_resolvable = True
        url.not_resolvable_since = datetime.now(pytz.utc)
        url.not_resolvable_reason = "No IPv4 or IPv6 address found in http scanner."
        url.save()
        # todo: then kill all endpoints on this url for http and https?
        # url not resolvable.
        return
    else:
        # if the domain was not resolvable, it surely is now. Undo resolvability.
        if url.not_resolvable:
            url.not_resolvable = False
            url.not_resolvable_since = datetime.now(pytz.utc)
            url.not_resolvable_reason = "Made resolvable again since ip address was found."
            url.save()

    try:
        # 10 seconds network timeout, 10 seconds timeout waiting for server response
        # a redirect means a server, so don't follow: much faster also.
        # todo: how to work with dropped connections?
        # todo: perhaps use httplib?
        r = requests.get(domain, timeout=(10, 10), allow_redirects=False)

        # 200, 418, who cares: http status code = http server and that is enough.
        if r.status_code:
            logger.debug("%s: status: %s" % (url, r.status_code))
            if ip4:
                save_endpoint(url, port, protocol, ip4)
            if ip6:
                save_endpoint(url, port, protocol, ip6)

        else:
            logger.debug("No status code? Now what?! %s" % url)
    except (ConnectTimeout, Timeout, ReadTimeout) as Ex:
        logger.debug("%s: Timeout! - %s" % (url, Ex))
    except (ConnectionRefusedError, ConnectionError, HTTPError) as Ex:
        """
        Some errors really mean there is no site. Example is the ConnectionRefusedError: [Errno 61]
        which means the endpoint can be killed.

        Yet...

        There can be many, many, many errors that still can be translated into an existing site.

        Until now we've found in responses:
        - BadStatusLine
        - CertificateError
        - certificate verify failed

        This all indicates that there is a service there. So this is stored.

        """
        # Nope: EOF occurred in violation of protocol
        # Nope: also: fine, a response! :) - youll get an unexpected closed connection.
        logger.debug("%s: NOPE! - %s" % (url, Ex))
        strerror = Ex.args  # this can be multiple.  # zit in nested exception?
        # logger.debug("Error message: %s" % strerror)
        strerror = str(strerror)  # Cast whatever we get back to a string. Instead of trace.
        if "BadStatusLine" in strerror or "CertificateError" in strerror or \
                                          "certificate verify failed" in strerror:
            logger.debug("Received BadStatusLine or CertificateError, which is an answer. "
                         "Still creating endpoint.")
            if ip4:
                save_endpoint(url, port, protocol, ip4)
            if ip6:
                save_endpoint(url, port, protocol, ip6)
        else:
            if ip4:
                kill_endpoint(url, port, protocol, ip4)
            if ip6:
                kill_endpoint(url, port, protocol, ip6)


def resolves(url):
    (ip4, ip6) = get_ips(url)
    if ip4 or ip6:
        return True
    return False


def get_ips(url):
    ip4 = ""
    ip6 = ""

    try:
        ip4 = socket.gethostbyname(url)
    except Exception as ex:
        # when not known: [Errno 8] nodename nor servname provided, or not known
        logger.debug("Get IPv4 error: %s" % ex)
        pass

    try:
        x = socket.getaddrinfo(url, None, socket.AF_INET6)
        ip6 = x[0][4][0]
    except Exception as ex:
        # when not known: [Errno 8nodename nor servname provided, or not known
        logger.debug("Get IPv6 error: %s" % ex)
        pass

    logger.debug("%s has IPv4 address: %s" % (url, ip4))
    logger.debug("%s has IPv6 address: %s" % (url, ip6))
    return ip4, ip6


def has_internet_connection(host="8.8.8.8", port=53, timeout=10):
    """
    https://stackoverflow.com/questions/3764291/checking-network-connection#3764660
    Host: 8.8.8.8 (google-public-dns-a.google.com)
    OpenPort: 53/tcp
    Service: domain (DNS/TCP)
    """
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except Exception as ex:
        logger.debug("No internet connection: %s" % ex)
        return False


def save_endpoint(url, port, protocol, ip):
    # prevent duplication
    if not endpoint_exists(url, port, protocol, ip):
        endpoint = Endpoint()
        endpoint.port = port
        endpoint.url = url
        endpoint.protocol = protocol
        endpoint.domain = url.url
        endpoint.ip = ip
        endpoint.discovered_on = datetime.now(pytz.utc)
        # endpoint.dossier = "Found using the http scanner."  #
        endpoint.save()
        logger.info("Added endpoint added to database: %s" % endpoint)
    else:
        logger.debug("Endpoint based on parameters was already in database.")

    return


def endpoint_exists(url, port, protocol, ip):
    return Endpoint.objects.all().filter(url=url,
                                         port=port,
                                         ip=ip,
                                         protocol=protocol,
                                         is_dead=False).count()


def kill_endpoint(url, port, protocol, ip):

    eps = Endpoint.objects.all().filter(url=url,
                                        port=port,
                                        ip=ip,
                                        protocol=protocol,
                                        is_dead=False)

    # todo: check if there is something attached to the endpoint?
    for ep in eps:
        ep.is_dead = True
        ep.is_dead_since = datetime.now(pytz.utc)
        ep.is_dead_reason = "Not found in HTTP Scanner anymore."
        ep.save()
