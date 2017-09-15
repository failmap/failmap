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
import socket
from datetime import datetime

import pytz
import requests
from requests.exceptions import ConnectionError

from failmap_admin.organizations.models import Url

from .models import Endpoint


# todo: separating finding IP adresses and endpoints.
class ScannerHttp:

    def scan(self):
        # clean url: add http and portnumber 80. Try other ports later.
        urls = Url.objects.all()
        for url in urls:
            ScannerHttp.scan_url(url, 80, "http")
        return

    @staticmethod
    def scan_multithreaded(port=80, protocol="http", only_new=False):

        if not only_new:
            urls = Url.objects.all()  # scans ALL urls.
        else:
            # todo: only new urls, those that don't have an endpoint on the protocol+port.
            # not without _any_ endpoint, given that there will soon be endpoints for it.
            # this also re-verifies all domains that explicitly don't have an endpoint on this
            # port+protocol, which can be a bit slow. (we're not saving it reversely).
            # todo: this is not correct yet.
            urls = Url.objects.all().exclude(endpoint__port=port, endpoint__protocol=protocol)
            urls = Url.objects.all()

        from multiprocessing import Pool
        pool = Pool(processes=8)

        if not ScannerHttp.has_internet_connection():
            print("No internet connection! Try again later!")
            return

        if protocol not in ["http", "https"]:
            print("Invalid protocol %s, options are: http, https" % protocol)
            return

        if port > 65535 or port < 0:
            print("Invalid port number, must be between 0 and 65535. %s" % port)
            return

        for url in urls:
            pool.apply_async(ScannerHttp.scan_url, [url, port, protocol],
                             callback=ScannerHttp.success_callback,
                             error_callback=ScannerHttp.error_callback)
        print("Closing pool")
        pool.close()
        print("Joining pool")
        pool.join()

    @staticmethod
    def success_callback(x):
        print("Success!")

    @staticmethod
    def error_callback(x):
        print("Error callback!")
        print(x)
        print(vars(x))

    # Simple: if there is a http response (status code), there is a http server.
    # There might be other protocols on standard ports.
    # Even if the IP constantly changes, we know that a scanner will find something by url
    # todo: check if we can scan https, due to our https lib not supporting "rest of world"
    # todo: check headers using another scanner, don't use this one, even though it contacts
    # the server (?)
    # todo: further look into dig, which at the moment doesn't return more than what we have...
    # We don't make endpoints for servers that don't exist: as opposed to qualys, since that
    # scanner is slow. (perhaps we should in that case?)
    # todo: option to not find IP's, only use existing ip's of endpoints / urls.
    @staticmethod
    def scan_url(url, port=80, protocol="https"):
        domain = "%s://%s:%s" % (protocol, url.url, port)
        print("Scanning http(s) server on: %s" % domain)

        (ip4, ip6) = ScannerHttp.get_ips(url.url)
#
        if not ip4 and not ip6:
            print("%s: No IPv4 or IPv6 address found. Url not resolvable?" % url)
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
            r = requests.get(domain, timeout=(10, 10))

            # 200, 418, who cares: http status code = http server and that is enough.
            if r.status_code:
                print("%s: status: %s" % (url, r.status_code))
                if ip4:
                    ScannerHttp.save_endpoint(url, port, protocol, ip4)
                if ip6:
                    ScannerHttp.save_endpoint(url, port, protocol, ip6)
            else:
                print("No status code? Now what?! %s" % url)
        except (ConnectionRefusedError, ConnectionError) as Ex:
            # ConnectionRefusedError: [Errno 61] Connection refused
            # What type of errors do we get when there is no internets?
            print("%s: NOPE! - %s" % (url, Ex))
            if ip4:
                ScannerHttp.kill_endpoint(url, port, protocol, ip4)
            if ip6:
                ScannerHttp.kill_endpoint(url, port, protocol, ip6)

    @staticmethod
    def resolves(url):
        (ip4, ip6) = ScannerHttp.get_ips(url)
        if ip4 or ip6:
            return True
        return False

    @staticmethod
    def get_ips(url):
        ip4 = ""
        ip6 = ""

        try:
            ip4 = socket.gethostbyname(url)
        except Exception as ex:
            # when not known: [Errno 8] nodename nor servname provided, or not known
            print("Get IPv4 error: %s" % ex)
            pass

        try:
            x = socket.getaddrinfo(url, None, socket.AF_INET6)
            ip6 = x[0][4][0]
        except Exception as ex:
            # when not known: [Errno 8nodename nor servname provided, or not known
            print("Get IPv6 error: %s" % ex)
            pass

        print("%s has IPv4 address: %s" % (url, ip4))
        print("%s has IPv6 address: %s" % (url, ip6))
        return ip4, ip6

    @staticmethod
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
            print("No internet connection: %s" % ex)
            return False

    @staticmethod
    def save_endpoint(url, port, protocol, ip):
        # prevent duplication
        if not ScannerHttp.endpoint_exists(url, port, protocol, ip):
            endpoint = Endpoint()
            endpoint.port = port
            endpoint.url = url
            endpoint.protocol = protocol
            endpoint.domain = url.url
            endpoint.ip = ip
            endpoint.discovered_on = datetime.now(pytz.utc)
            # endpoint.dossier = "Found using the http scanner."  #
            endpoint.save()

        return

    @staticmethod
    def endpoint_exists(url, port, protocol, ip):
        return Endpoint.objects.all().filter(url=url,
                                             port=port,
                                             ip=ip,
                                             protocol=protocol,
                                             is_dead=False).count()

    @staticmethod
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
