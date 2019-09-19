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
from datetime import datetime
from ipaddress import AddressValueError

import pytz
import requests
# suppress InsecureRequestWarning, we do those request on purpose.
import urllib3
from celery import Task, group
from django.conf import settings
from requests import ConnectTimeout, HTTPError, ReadTimeout, Request, Session, Timeout
from requests.exceptions import ConnectionError

from websecmap.celery import app
from websecmap.organizations.models import Organization, Url
from websecmap.scanners.models import Endpoint, UrlIp
from websecmap.scanners.scanner.__init__ import (allowed_to_discover_endpoints, endpoint_filters,
                                                 q_configurations_to_scan)
from websecmap.scanners.timeout import timeout

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger(__package__)

# don't contact http/443 and https/80. You can, but that is 99.99 waste data.
STANDARD_HTTP_PORTS = [80, 8008, 8080]
STANDARD_HTTPS_PORTS = [443, 8443]
PREFERRED_PORT_ORDER = [443, 80, 8443, 8080, 8008]


"""
http://2.python-requests.org/en/master/user/advanced/?highlight=timeout%3D#timeouts

The connect timeout is the number of seconds Requests will wait for your client to establish a connection to a
remote machine (corresponding to the connect()) call on the socket. It’s a good practice to set connect timeouts
to slightly larger than a multiple of 3, which is the default TCP packet retransmission window.

1 second is surely too short, it results in a lot of false positives, especially when scanning a lot of sites.
"""
CONNECT_TIMEOUT = 10

"""
Once your client has connected to the server and sent the HTTP request, the read timeout is the number of seconds the
client will wait for the server to send a response. (Specifically, it’s the number of seconds that the client will wait
between bytes sent from the server. In 99.9% of cases, this is the time before the server sends the first byte).
"""
READ_TIMEOUT = 10


# Discover Endpoints generic task

# todo: in wildcard scenarios you can add urls that have a deviating IP from the (loadbalanced) wildcard address.


def compose_discover_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
    **kwargs
) -> Task:
    """Compose taskset to scan specified endpoints.

    *This is an implementation of `compose_discover_task`.
    For more documentation about this concept, arguments and concrete
    examples of usage refer to `compose_discover_task` in `types.py`.*

    """

    if not allowed_to_discover_endpoints("http"):
        return group()

    if organizations_filter:
        organizations = Organization.objects.filter(**organizations_filter)
        # apply filter to urls in organizations (or if no filter, all urls)
        urls = Url.objects.filter(q_configurations_to_scan(), organization__in=organizations, **urls_filter)
        urls = list(set(urls))
        log.info('Creating http scan task for %s urls for %s organizations.', len(urls), len(organizations))
    else:
        urls = Url.objects.filter(q_configurations_to_scan(), **urls_filter)
        urls = list(set(urls))
        log.info('Creating http scan task for %s urls.', len(urls))

    if endpoints_filter:
        log.warning("Endpoint filters are not implemented: filter has no effect.")

    # make sure we're dealing with a list for the coming random function

    # randomize the endpoints to better spread load over urls.
    random.shuffle(urls)
    tasks = []
    ip_versions = [4, 6]

    # even with a randomized url order, still try to add as much time as possible between contacting
    # the same url, to not disrupt running services.

    # We found we're getting useless endpoints that contain little to no data when
    # opening non-tls port 443 and tls port 80. We're not doing that anymore.

    # DONE: create separate tasks on different queues determined by IP version. Distribute load per capability.
    # todo: don't use the canvas model, just fire off the next task from the connection.
    # The canvas model uses an enormous amount of CPU, which is needed for other things.

    # why do we want to store these at all? They change all the time and well... we don't do anything with this info
    # so no hoarding and disable this for when we need it.
    # for url in urls:
    #     tasks.append(get_ips.si(url.url) | url_lives.s(url))  # See if thing is alive, once.

    for ip_version in ip_versions:
        queue = "ipv4" if ip_version == 4 else "ipv6"

        for port in PREFERRED_PORT_ORDER:

            if port in STANDARD_HTTP_PORTS:
                for url in urls:
                    tasks.append(
                        can_connect.si(
                            protocol="http",
                            url=url,
                            port=port,
                            ip_version=ip_version
                        ).set(queue=queue)
                        | connect_result.s(protocol="http", url=url, port=port, ip_version=ip_version)
                    )

            if port in STANDARD_HTTPS_PORTS:
                for url in urls:
                    tasks.append(
                        can_connect.si(
                            protocol="https",
                            url=url,
                            port=port,
                            ip_version=ip_version
                        ).set(queue=queue)
                        | connect_result.s(protocol="https", url=url, port=port, ip_version=ip_version)
                    )

    return group(tasks)


def compose_verify_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
    **kwargs
) -> Task:
    """Verifies existing https and http endpoints. Is pretty quick, as it will not stumble upon non-existing services
    as much.
    """

    if not allowed_to_discover_endpoints("http"):
        return group()

    # todo: do we need a generic resurrect task and also check for , 'is_dead': False here?
    # otherwise we'll be verifying things that existed ages ago and probably will never return. Which makes this
    # scan also extremely slow. - The description says we should.
    default_filter = {"protocol__in": ["https", "http"], "is_dead": False}
    endpoints_filter = {**endpoints_filter, **default_filter}
    endpoints = Endpoint.objects.all().filter(q_configurations_to_scan(level='endpoint'), **endpoints_filter)
    endpoints = endpoint_filters(endpoints, organizations_filter, urls_filter, endpoints_filter)

    tasks = []
    for endpoint in endpoints:
        queue = "ipv4" if endpoint.ip_version == 4 else "ipv6"
        tasks.append(can_connect.si(protocol=endpoint.protocol, url=endpoint.url,
                                    port=endpoint.port, ip_version=endpoint.ip_version).set(queue=queue)
                     | connect_result.s(protocol=endpoint.protocol, url=endpoint.url,
                                        port=endpoint.port, ip_version=endpoint.ip_version))
    return group(tasks)


@app.task(queue="storage")
def url_lives(ips, url):
    """
    This results in problems in celery, so we're doing it the old sequential way.
    And given this is all storage stuff anyway...
    chain(
        get_ips.si(url.url),
        group(store_url_ips_task.s(url),
              kill_url_task.s(url),
              revive_url_task.s(url),
              ),
    ),
    """

    store_url_ips(url, ips)

    if not any(ips) and not url.not_resolvable:
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
    else:
        # revive url
        if url.not_resolvable:
            url.not_resolvable = False
            url.not_resolvable_since = datetime.now(pytz.utc)
            url.not_resolvable_reason = "Made resolvable again since ip address was found."
            url.save()


@app.task(queue="4and6")
def get_ips(url: str):
    ipv4 = ""
    ipv6 = ""

    if settings.NETWORK_SUPPORTS_IPV4:
        ipv4 = get_ipv4(url)

    if settings.NETWORK_SUPPORTS_IPV6:
        ipv6 = get_ipv6(url)

    return ipv4, ipv6


# It's possible you don't get an address back, it could not be configured on our or their side.
def get_ipv4(url: str):
    # https://www.iana.org/assignments/iana-ipv4-special-registry/iana-ipv4-special-registry.xhtml
    ipv4 = ""

    try:
        ipv4 = socket.gethostbyname(url)
        log.debug("%s has IPv4 address: %s" % (url, ipv4))
    except Exception as ex:
        # when not known: [Errno 8] nodename nor servname provided, or not known
        log.debug("Get IPv4 error on %s: %s" % (url, ex))

    # the contents of the DNS record can be utter garbage, there is absolutely no guarantee that this is an IP
    # it could be an entire novel, or images
    try:
        if ipv4:
            address = ipaddress.IPv4Address(ipv4)
            if not address.is_global:
                ipv4 = ""
    except (AddressValueError, ValueError):
        log.debug("IPv4 address was not recognized on %s: %s" % (url, ipv4))
        ipv4 = ""

    return ipv4


# It's possible you don't get an address back, it could not be configured on our or their side.
def get_ipv6(url: str):
    # https://www.iana.org/assignments/iana-ipv6-special-registry/iana-ipv6-special-registry.xhtml
    ipv6 = ""

    try:
        # dig AAAA faalkaart.nl +short (might be used for debugging)
        x = socket.getaddrinfo(url, None, socket.AF_INET6)
        ipv6 = x[0][4][0]

        # six to four addresses make no sense
        if str(ipv6).startswith("::ffff:"):
            log.debug("Six-to-Four address %s discovered on %s, "
                      "did you configure IPv6 connectivity correctly? "
                      "Removing this IPv6 address from result to prevent "
                      "database pollution." %
                      (ipv6, url))
            ipv6 = ""
        else:
            log.debug("%s has IPv6 address: %s" % (url, ipv6))
    except Exception as ex:
        # when not known: [Errno 8nodename nor servname provided, or not known
        log.debug("Get IPv6 error on %s: %s" % (url, ex))

    try:
        if ipv6:
            address = ipaddress.IPv6Address(ipv6)
            if not address.is_global:
                ipv6 = ""
    except (AddressValueError, ValueError):
        log.debug("IPv6 address was not recognized on %s: %s" % (url, ipv6))
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


@app.task(queue="4and6", rate_limit='120/s', bind=True)
def can_connect(self, protocol: str, url: Url, port: int, ip_version: int) -> bool:
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
    """

    # You can see what queue / routing info is used. So options(queue works and overrides the default 4and6 queue)
    # log.info(self.request['delivery_info']['routing_key'])

    uri = ""
    ip = ""
    if ip_version == 4:
        ip = get_ipv4(url.url)
        uri = "%s://%s:%s" % (protocol, ip, port)
    else:
        ip = get_ipv6(url.url)
        uri = "%s://[%s]:%s" % (protocol, ip, port)

    if not ip:
        return False

    log.debug("Attempting connect on: %s: host: %s IP: %s" % (uri, url.url, ip))

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
        r = requests.get(uri, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                         allow_redirects=False,  # redirect = connection
                         verify=False,  # any tls = connection
                         headers={'Host': url.url,
                                  'User-Agent': get_random_user_agent()})
        if r.status_code:
            log.debug("%s: Host: %s Status: %s" % (uri, url.url, r.status_code))
            return True
        else:
            log.debug("No status code? Now what?! %s" % url)
            # probably never reached, exception thrown when no status code is present
            return True
    except (ConnectTimeout, Timeout, ReadTimeout) as Ex:
        log.debug("%s: Timeout! - %s" % (url, Ex))
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
        log.debug("%s: Exception returned: %s" % (url, Ex))
        strerror = Ex.args  # this can be multiple.  # zit in nested exception?
        strerror = str(strerror)  # Cast whatever we get back to a string. Instead of trace.
        if any(["BadStatusLine" in strerror,
                "CertificateError" in strerror,
                "certificate verify failed" in strerror,
                "bad handshake" in strerror]):
            log.debug("Exception indicates that there is a server, but we're not able to "
                      "communicate with it correctly. Error: %s" % strerror)
            return True
        else:
            log.debug("Exception indicates we could not connect to server. Error: %s" % strerror)

            # This might be due to the fact that a firewall is blocking direct requests to the IP with a different
            # host. Seen this in edienstenburgerzaken.purmerend.nl, which is annoying. So we're going to try
            # to connect again, but then with the normal host, without IP. Note that this requires that the
            # correct queue is used to connect to the network. This might not work on your development machine
            # as it might connect over the wrong network

            # Basically perform the same checks on the url directly, with a more extensive request that can be debugged

            try:
                log.debug("Trying again with a matching url and host header -> No connection to IP with a host header.")

                s = Session()

                uri = "%s://%s:%s" % (protocol, url.url, port)

                req = Request('GET', uri, headers={'Host': url.url, 'User-Agent': get_random_user_agent()})
                prepped = s.prepare_request(req)

                # pretty_print_request(prepped)

                s.send(prepped, verify=False, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), allow_redirects=False,)

                return True
            except (ConnectionRefusedError, ConnectionError, HTTPError) as Ex:
                # Same handling as above.
                strerror = Ex.args
                strerror = str(strerror)

                if any([error in strerror for error in ["BadStatusLine", "CertificateError",
                                                        "certificate verify failed", "bad handshake"]]):
                    log.debug("Exception indicates that there is a server, but we're not able to "
                              "communicate with it correctly. Error: %s" % strerror)
                    return True
            except (ConnectTimeout, Timeout, ReadTimeout):
                return False

            # At this point we might have received a different exception. Let's see which ones...
            log.debug("Did also not connect using the hostname as url. Giving up.")
            return False


# thank you https://stackoverflow.com/questions/20658572/python-requests-print-entire-http-request-raw
def pretty_print_request(req):
    """
    At this point it is completely built and ready
    to be fired; it is "prepared".

    However pay attention at the formatting used in
    this function because it is programmed to be pretty
    printed and may differ from the actual request.
    """
    print('{}\n{}\n{}\n\n{}'.format(
        '-----------START-----------',
        req.method + ' ' + req.url,
        '\n'.join('{}: {}'.format(k, v) for k, v in req.headers.items()),
        req.body,
    ))


@app.task(queue='storage')
def connect_result(result, protocol: str, url: Url, port: int, ip_version: int):
    log.info("%s %s/%s IPv%s: %s" % (url, protocol, port, ip_version, result))

    if result:
        save_endpoint(protocol, url, port, ip_version)
    else:
        kill_endpoint(protocol, url, port, ip_version)
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
    except Exception as ex:
        log.debug("No internet connection: %s" % ex)
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
        log.info("Added endpoint added to database: %s" % endpoint)
    else:
        log.debug("Endpoint based on parameters was already in database.")
    return


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
        try:
            epip.rdns_name = get_rdns_name(ip)
        except TimeoutError:
            # we'll have to do without.
            epip.rdns_name = ""
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
        # host doesn't exist / unknown host
        pass
    except BaseException as e:
        log.error('Unknown rdns failure %s on ip %s' % (str(e), ip))

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


@app.task(queue='4and6')
def check_network(code_location=""):
    """
    Used to see if a worker can do IPv6. Will trigger an exception when no ipv4 or ipv6 is available,
    which is logged in sentry and other logs.

    :return:
    """

    log.info("Testing network connection via %s." % code_location)

    log.info("IPv4 is enabled via configuration: %s" % settings.NETWORK_SUPPORTS_IPV4)
    log.info("IPv6 is enabled via configuration: %s" % settings.NETWORK_SUPPORTS_IPV6)

    url = Url()
    url.url = "faalkaart.nl"

    can_ipv4 = can_connect("https", url, 443, 4)
    can_ipv6 = can_connect("https", url, 443, 6)

    if not can_ipv4 and not can_ipv6:
        raise ConnectionError("Both ipv6 and ipv4 networks could not be reached via %s."
                              "IPv4 enabled in config: %s, IPv6 enabled in config: %s" %
                              (code_location, settings.NETWORK_SUPPORTS_IPV4, settings.NETWORK_SUPPORTS_IPV6))

    if not can_ipv4:
        raise ConnectionError("Could not reach IPv4 Network via %s. IPv4 enabled in config: %s" %
                              (code_location, settings.NETWORK_SUPPORTS_IPV4))
    else:
        log.info("IPv4 could be reached via %s" % code_location)

    if not can_ipv6:
        raise ConnectionError("Could not reach IPv6 Network via %s. IPv6 enabled in config: %s" %
                              (code_location, settings.NETWORK_SUPPORTS_IPV6))
    else:
        log.info("IPv6 could be reached via %s" % code_location)


def redirects_to_safety(endpoint: Endpoint):
    """
    Also includes the ip-version of the endpoint. Implies that the endpoint resolves.
    Any safety over any network is accepted now, both A and AAAA records.

    To enable debugging: logging.basicConfig(level=logging.DEBUG)

    :param endpoint:
    :return:
    """
    import requests
    from requests import ReadTimeout, ConnectTimeout, HTTPError, Timeout, ConnectionError

    # The worker (should) only resolve domain names only over ipv4 or ipv6. (A / AAAA).
    # Currenlty docker does not support that. Which means a lot of network rewriting for dealing with
    # all edge cases of HTTP.
    uri = endpoint.uri_url()

    # A feature of requests is to send any headers you've sent when there are redirects.
    # This becomes problematic when you set the Host header. This prevents

    try:
        session = requests.Session()
        response = session.get(
            uri,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),  # allow for insane network lag
            allow_redirects=True,  # point is: redirects to safety
            verify=False,  # certificate validity is checked elsewhere, having some https > none

            # redirects do NOT overwrite the host headers. Meaning that following a redirect, the
            # host header is set, which is incorrect. The Host header should only be set in the first
            # request, and should be overwritten by all subsequent requests.
            # The reason we set the host header explicitly, is because we want to contact the webserver
            # via the IP address, so we can explicitly contect IPv4 and IPv6 addresses of this domain.
            # issue was logged here: https://github.com/psf/requests/issues/5196
            headers={'User-Agent': get_random_user_agent(),
                     # Give some instructions that we want a secure address...
                     'Upgrade-Insecure-Requests': "1"})

        if response.history:
            log.debug("Request was redirected, there is hope. Redirect path:")
            for index, resp in enumerate(response.history):
                log.debug(f"- Redirect {index}: {resp.url}.")
            log.debug("Final destination:")
            log.debug(f"{response.status_code}: {response.url}")

            if response.url.startswith("https://"):
                log.debug("Url starts with https, so it redirects to safety.")
                return True
            log.debug("Url is not redirecting to a safe url.")
            return False
        else:
            log.debug("Request was not redirected, so not going to a safe url.")
            return False
    except (ConnectTimeout, HTTPError, ReadTimeout, Timeout, ConnectionError, requests.exceptions.TooManyRedirects
            ) as e:
        log.debug("Request resulted into an error, it's not redirecting properly.")
        log.debug(f"The error retrieved was: {e}")
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

        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.14; rv:64.0) Gecko/20100101 Firefox/64.0"
    ]

    return random.choice(user_agents)
