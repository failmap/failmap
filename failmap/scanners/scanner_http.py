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
import random
import socket
from datetime import datetime
from typing import List

import pytz
import requests
# suppress InsecureRequestWarning, we do those request on purpose.
import urllib3
from celery import Task, chain, group
from django.conf import settings
from requests import ConnectTimeout, HTTPError, ReadTimeout, Timeout
from requests.exceptions import ConnectionError

from failmap.celery import app
from failmap.organizations.models import Organization, Url
from failmap.scanners.models import Endpoint, UrlIp

from .scanner import allowed_to_scan, q_configurations_to_scan
from .timeout import timeout

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__package__)

# don't contact http/443 and https/80. You can, but that is 99.99 waste data.
STANDARD_HTTP_PORTS = [80, 8008, 8080]
STANDARD_HTTPS_PORTS = [443, 8443]

# Discover Endpoints generic task


@app.task(queue="storage")
def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    """Compose taskset to scan specified endpoints.

    *This is an implementation of `compose_task`. For more documentation about this concept, arguments and concrete
    examples of usage refer to `compose_task` in `types.py`.*

    """

    if not allowed_to_scan("scanner_http"):
        return group()

    if organizations_filter:
        organizations = Organization.objects.filter(**organizations_filter)
        # apply filter to urls in organizations (or if no filter, all urls)
        urls = Url.objects.filter(q_configurations_to_scan(), organization__in=organizations, **urls_filter)
        logger.info('Creating scan task for %s urls for %s organizations.', len(urls), len(organizations))
    else:
        urls = Url.objects.filter(q_configurations_to_scan(), **urls_filter)
        logger.info('Creating scan task for %s urls.', len(urls))

    if endpoints_filter:
        logger.warning("Endpoint filters are not implemented: filter has no effect.")

    # make sure we're dealing with a list for the coming random function
    urls = list(urls)
    # randomize the endpoints to better spread load over urls.
    random.shuffle(urls)
    tasks = []

    # even with a randomized url order, still try to add as much time as possible between contacting
    # the same url, to not disrupt running services.

    # We found we're getting useless endpoints that contain little to no data when
    # opening non-tls port 443 and tls port 80. We're not doing that anymore.
    for port in STANDARD_HTTP_PORTS:
        for url in urls:
            tasks.append(resolve_and_scan_tasks(protocol="http", url=url, port=port))

    for port in STANDARD_HTTPS_PORTS:
        for url in urls:
            tasks.append(resolve_and_scan_tasks(protocol="https", url=url, port=port))

    return group(tasks)


def validate_port(port: int):
    if port > 65535 or port < 0:
        logger.error("Invalid port number, must be between 0 and 65535. %s" % port)
        raise ValueError("Invalid port number, must be between 0 and 65535. %s" % port)


def validate_protocol(protocol: str):
    if protocol not in ["http", "https"]:
        logger.error("Invalid protocol %s, options are: http, https" % protocol)
        raise ValueError("Invalid protocol %s, options are: http, https" % protocol)


def verify_endpoints(urls: List[Url]=None, port: int=None, protocol: str=None, organizations: List[Organization]=None):
    """
    Checks all http(s) endpoints if they still exist. This is to monitor changes in the existing
    dataset, without contacting an organization too often. It can be checked every few days,
    as trying to find new endpoints is more involved and should not be run more than once every
    two to four weeks.

    The only result this scanner has is the same or less endpoints than we currently have.

    Existing endpoints might be marked as unresolvable.

    :return: None
    """
    if not urls:
        endpoints = Endpoint.objects.all().filter(is_dead=False,
                                                  url__not_resolvable=False,
                                                  url__is_dead=False)
    else:
        endpoints = Endpoint.objects.all().filter(is_dead=False,
                                                  url__not_resolvable=False,
                                                  url__is_dead=False,
                                                  url__in=urls)

    if port:
        endpoints = endpoints.filter(port=port)

    if protocol:
        endpoints = endpoints.filter(protocol=protocol)
    else:
        endpoints = endpoints.filter(protocol__in=["http", "https"])

    if organizations:
        endpoints = endpoints.filter(url__organization__in=organizations)

    # randomize the endpoints to better spread load.
    endpoints = list(endpoints)
    random.shuffle(endpoints)

    for endpoint in endpoints:
        scan_url(endpoint.protocol, endpoint.url, endpoint.port)


# TODO: make queue explicit, split functionality in storage and scanner
@app.task
def discover_endpoints(urls: List[Url]=None, port: int=None, protocol: str=None,
                       organizations: List[Organization]=None):
    """
    Contact each URL (or each url of organizations) to determine if there are endpoints.
    Do so both over HTTP, HTTPS on various ports and with both IPv4 and IPv6.

    A healthy set of endpoints in 2018 is:


    IPv4 80  Redirects to 443
    IPv4 443 Content
    IPv6 80  Redirects to 443
    IPv6 443 Content

    Port 80 websites will be deprecated in the coming years by all popular browsers. They will begin to
    disappear, which will be in full force in mid 2019.

    Existing endpoints might be marked as unresolvable.
    Existing URLS might also be marked as unresolvable: the is_dead will not be set, this is a OSI layer 8 option.

    :return: None
    """
    if not urls:
        urls = Url.objects.all().filter(is_dead=False, not_resolvable=False)

    if organizations:
        urls = urls.filter(organization__in=organizations)

    if protocol:
        protocols = [protocol]
    else:
        protocols = ["https"]

    if port:
        ports = [port]
    else:
        # Yes, HTTP sites on port 443 exist, we've seen many of them. Not just warnings(!).
        # Don't underestimate the flexibility of the internet.
        ports = STANDARD_HTTPS_PORTS

    # make sure we're dealing with a list for the coming random function
    urls = list(urls)
    # randomize the endpoints to better spread load over urls.
    random.shuffle(urls)

    scan_urls(protocols, urls, ports)


def scan_urls_on_standard_ports(urls: List[Url]):
    scan_urls(["http"], urls, STANDARD_HTTP_PORTS)
    scan_urls(["https"], urls, STANDARD_HTTPS_PORTS)


@app.task
def discover_endpoints_on_standard_ports(urls: List[Url]):
    scan_urls(["http"], urls, STANDARD_HTTP_PORTS)
    scan_urls(["https"], urls, STANDARD_HTTPS_PORTS)


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


# TODO: make queue explicit, split functionality in storage and scanner
def scan_url(protocol: str, url: Url, port: int):
    resolve_task = resolve_and_scan.s(protocol, url, port)
    resolve_task.apply_async()


def scan_url_direct(protocol: str, url: Url, port: int):
    resolve_and_scan(protocol, url, port)


# todo: apply rate limiting
# also rate limited for the same reason as can_connect is rate limited.
# would this be faster the ip discovery and actual scan grow to far apart.
# also it would mean an intense series of questions to the dns server.
# TODO: make queue explicit, split functionality in storage and scanner
@app.task(ignore_result=True, queue="scanners")
def resolve_and_scan(protocol: str, url: Url, port: int):
    ips = get_ips(url.url)

    # this can take max 20 seconds, no use to wait
    store_task = store_url_ips.s(url, ips)  # administrative, does reverse dns query
    store_task.apply_async()

    # todo: this should be re-checked a few times before it's really killed. Retry?
    if not any(ips):
        kill_url_task = kill_url.s(url)  # administrative
        kill_url_task.apply_async()
        return

    # this is not a stacking solution. Weird. Why not?
    url_revive_task = revive_url.s(url)
    url_revive_task.apply_async()

    (ipv4, ipv6) = ips
    if ipv4:
        # http://docs.celeryproject.org/en/latest/reference/celery.html#celery.signature
        connect_task = can_connect.s(protocol=protocol, url=url, port=port, ip=ipv4).set(
            queue='scanners.endpoint_discovery.ipv4')
        result_task = connect_result.s(protocol, url, port, 4)  # administrative task
        task = (connect_task | result_task)
        task.apply_async()

    if ipv6:
        connect_task = can_connect.s(protocol=protocol, url=url, port=port, ip=ipv6).set(
            queue='scanners.endpoint_discovery.ipv6')
        result_task = connect_result.s(protocol, url, port, 6)  # administrative task
        task = (connect_task | result_task)
        task.apply_async()


def resolve_and_scan_tasks(protocol: str, url: Url, port: int):

    # todo: give ips als argument in kill an revive.
    task = group(
        chain(
            get_ips.si(url.url),
            group(store_url_ips_task.s(url),
                  kill_url_task.s(url),
                  revive_url_task.s(url),
                  ),
        ),
        (get_ips.si(url.url) | can_connect_ips.s(protocol, url, port, 4) | connect_result.s(protocol, url, port, 4)),
        (get_ips.si(url.url) | can_connect_ips.s(protocol, url, port, 6) | connect_result.s(protocol, url, port, 6)),
    )
    return task


@app.task(queue="scanners")
def can_connect_ips(ips, protocol, url, port, ip_version):
    ipv4, ipv6 = ips
    if ip_version == 4:
        return can_connect(protocol, url, port, ipv4)

    if ip_version == 6:
        return can_connect(protocol, url, port, ipv6)


@app.task(queue="scanners")
def get_ips(url: str):
    ipv4 = ""
    ipv6 = ""

    if settings.NETWORK_SUPPORTS_IPV4:
        try:
            ipv4 = socket.gethostbyname(url)
            logger.debug("%s has IPv4 address: %s" % (url, ipv4))
        except Exception as ex:
            # when not known: [Errno 8] nodename nor servname provided, or not known
            logger.debug("Get IPv4 error: %s" % ex)

    if settings.NETWORK_SUPPORTS_IPV6:
        try:
            # dig AAAA faalkaart.nl +short (might be used for debugging)
            x = socket.getaddrinfo(url, None, socket.AF_INET6)
            ipv6 = x[0][4][0]

            # six to four addresses make no sense
            if str(ipv6).startswith("::ffff:"):
                logger.error("Six-to-Four address %s discovered on %s, "
                             "did you configure IPv6 connectivity correctly? "
                             "Removing this IPv6 address from result to prevent "
                             "database pollution." %
                             (ipv6, url))
                ipv6 = ""
            else:
                logger.debug("%s has IPv6 address: %s" % (url, ipv6))
        except Exception as ex:
            # when not known: [Errno 8nodename nor servname provided, or not known
            logger.debug("Get IPv6 error: %s" % ex)

    return ipv4, ipv6


@app.task(
    # When doing a lot of connections, try to do them in semi-random order also not to overload networks/firewalls

    # Don't try and overload the network with too many connections.
    # The (virtual) network (card) might have a problem keeping up.
    # Firewalls might see it as hostile.
    # Our database might be overloaded with work,

    # To consider the rate limit:
    # There are about 11000 endpoints at this moment.
    # 3/s = 180/m = 1800/10m = 10800/h
    # 4/s = 240/m = 2400/10m = 14400/h
    # 5/s = 300/m = 3000/10m = 18000/h
    # 10/s = 600/m = 6000/10m = 36000/h

    # given many won't exist and time out, it's fine to set it to 20...

    # on the development machine it scans all within 10 minutes. About 20/s.

    rate_limit='120/s',
    # queue needs to be set based on ip, either scanners.endpoint_discovery.ipv4 or scanners.endpoint_discovery.ipv4
)
def can_connect(protocol: str, url: Url, port: int, ip: str) -> bool:
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

    # it might be that this is called without an IP, for example via celery code that doesn't know if an ipv4 or ipv6
    # result actually returned something. In such cases, no IP, means no endpoint.
    if not ip:
        return False

    if ":" in ip:
        uri = "%s://[%s]:%s" % (protocol, ip, port)
    else:
        uri = "%s://%s:%s" % (protocol, ip, port)

    logger.debug("Attempting connect on: %s: host: %s IP: %s" % (uri, url.url, ip))

    try:
        """
        30 seconds network timeout, 30 seconds timeout for server response.
        If we get a redirect, it means there is a server. Don't follow.

        Any status code is enough to verify that there is an endpoint.
        Some servers don't return a status code, that will trigger an exception (AttributeError)

        Some servers redirect to itself (or any host you throw at it):

        ipv4 = socket.gethostbyname("demo3.data.amsterdam.nl")

        r = requests.get("http://185.3.211.120:80", timeout=(30, 30), allow_redirects=False,
            headers={'Host': "demo3.data.amsterdam.nl"})
        r.headers
        {'Content-length': '0', 'Location': 'https://demo3.data.amsterdam.nl/', 'Connection': 'close'}

        We don't follow redirects, because we only want to know if there is something we can connect to.
        This can lead to interesting behavior: the browser times out.

        https://stackoverflow.com/questions/43156023/what-is-http-host-header#43156094

        # Certificate did not match expected hostname: 85.119.104.84.
        Certificate: {'subject': ((('commonName', 'webdiensten.drechtsteden.nl'),),)
        """
        r = requests.get(uri, timeout=(30, 30),
                         allow_redirects=False,  # redirect = connection
                         verify=False,  # any tls = connection
                         headers={'Host': url.url,
                                  'User-Agent': get_random_user_agent()})
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
                "certificate verify failed" in strerror,
                "bad handshake" in strerror]):
            logger.debug("Exception indicates that there is a server, but we're not able to "
                         "communicate with it correctly. Error: %s" % strerror)
            return True
        else:
            logger.debug("Exception indicates we could not connect to server. Error: %s" % strerror)
            return False


@app.task(queue='storage')
def connect_result(result, protocol: str, url: Url, port: int, ip_version: int):
    logger.info("%s %s" % (url, result))
    # log.info("%s %s" % (url, url))
    # log.info("%s %s" % (url, port))
    # log.info("%s %s" % (url, protocol))
    # log.info("%s %s" % (url, ip_version))

    if result:
        save_endpoint(protocol, url, port, ip_version)
    else:
        kill_endpoint(protocol, url, port, ip_version)

    # always give a positive result, so the chain continues(?)
    return True


def resolves(url: str):
    (ip4, ip6) = get_ips(url)
    if ip4 or ip6:
        return True
    return False


def resolves_on_v4(url: str):
    (ip4, ip6) = get_ips(url)
    if ip4:
        return True
    return False


def resolves_on_v6(url: str):
    (ip4, ip6) = get_ips(url)
    if ip6:
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


@app.task(queue='storage')
def revive_url_task(ips, url: Url):

    # don't revive if there are no ips
    if not any(ips):
        return

    """
    Sets a URL as resolvable. Does not touches the is_dead (layer 8) field.

    Todo:
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


@app.task(queue='storage')
def revive_url(url: Url):
    """
    Sets a URL as resolvable. Does not touches the is_dead (layer 8) field.

    Todo:
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


@app.task(queue='storage')
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

    Endpoint.objects.all().filter(url=url).update(is_dead=True,
                                                  is_dead_since=datetime.now(pytz.utc),
                                                  is_dead_reason="Url was killed")

    UrlIp.objects.all().filter(url=url).update(
        is_unused=True,
        is_unused_since=datetime.now(pytz.utc),
        is_unused_reason="Url was killed"
    )


@app.task(queue='storage')
def kill_url(url: Url):
    """
    Sets a URL as not resolvable. Does not touches the is_dead (layer 8) field.

    :param url:
    :return:
    """
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


# todo: split up between rdns and storing.
@app.task(queue='storage')
def store_url_ips_task(ips, url: Url):
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


@app.task(queue='storage')
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


@app.task(queue='scanners')
def check_network(code_location=""):
    """
    Used to see if a worker can do IPv6. Will trigger an exception when no ipv4 or ipv6 is available,
    which is logged in sentry and other logs.

    :return:
    """

    logger.info("Testing network connection via %s." % code_location)

    logger.info("IPv4 is enabled via configuration: %s" % settings.NETWORK_SUPPORTS_IPV4)
    logger.info("IPv6 is enabled via configuration: %s" % settings.NETWORK_SUPPORTS_IPV6)

    url = Url()
    url.url = "faalkaart.nl"

    ips = get_ips(url.url)

    can_ipv4, can_ipv6 = False, False

    (ipv4, ipv6) = ips
    if ipv4:
        can_ipv4 = can_connect("https", url, 443, ipv4)

    if ipv6:
        can_ipv6 = can_connect("https", url, 443, ipv6)

    if not can_ipv4 and not can_ipv6:
        raise ConnectionError("Both ipv6 and ipv4 networks could not be reached via %s."
                              "IPv4 enabled in config: %s, IPv6 enabled in config: %s" %
                              (code_location, settings.NETWORK_SUPPORTS_IPV4, settings.NETWORK_SUPPORTS_IPV6))

    if not can_ipv4:
        raise ConnectionError("Could not reach IPv4 Network via %s. IPv4 enabled in config: %s" %
                              (code_location, settings.NETWORK_SUPPORTS_IPV4))
    else:
        logger.info("IPv4 could be reached via %s" % code_location)

    if not can_ipv6:
        raise ConnectionError("Could not reach IPv6 Network via %s. IPv6 enabled in config: %s" %
                              (code_location, settings.NETWORK_SUPPORTS_IPV6))
    else:
        logger.info("IPv6 could be reached via %s" % code_location)


def redirects_to_safety(endpoint: Endpoint):
    """
    Also includes the ip-version of the endpoint.

    :param endpoint:
    :return:
    """
    import requests
    from requests import ReadTimeout, ConnectTimeout, HTTPError, Timeout, ConnectionError

    (ipv4, ipv6) = get_ips(endpoint.url.url)

    if endpoint.ip_version == 4:
        uri = "%s://%s:%s" % ("http", ipv4, "80")
    else:
        uri = "%s://[%s]:%s" % ("http", ipv6, "80")

    try:
        response = requests.get(uri,
                                timeout=(30, 30),  # allow for insane network lag
                                allow_redirects=True,  # point is: redirects to safety
                                verify=False,  # certificate validity is checked elsewhere, having some https > none
                                headers={'Host': endpoint.url.url,
                                         'User-Agent': get_random_user_agent()})
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
    except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError, requests.exceptions.TooManyRedirects):
        logger.debug("Request resulted into an error, it's not redirecting properly.")
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
        "(KHTML, like Gecko) Chrome/47.0.2526.111 Safari/537.36"
    ]

    return random.choice(user_agents)
