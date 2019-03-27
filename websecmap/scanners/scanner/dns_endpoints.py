"""
This discovers endpoints that are used for the Internet.NL scanners. The internet.nl scanners require only the
existence of AAAA or A DNS records for web and SOA for mail. This means this discovery will find DNS-record type
endpoints that equal normal endpoints. Except they don't have a port and ip_version.

It's not worth the while to make a new, special, 'DNS endpoint' type, as the reporting and life cycle will be just
the same. So to save a lot of pain and trouble, we'll just fill the port and ip_version with 0.

# todo: can we check if the mail is routed outside of the country somehow? Due to privacy concerns / GDPR?
"""

import logging
from time import sleep

from celery import Task, group
from dns.resolver import NXDOMAIN, NoAnswer, NoNameservers, Resolver
from tenacity import before_log, retry, stop_after_attempt, wait_exponential

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint
from websecmap.scanners.scanner.__init__ import (endpoint_filters, q_configurations_to_scan,
                                                 url_filters)
from websecmap.scanners.scanner.http import connect_result

log = logging.getLogger(__name__)


# cloudflare, google, quad9, cisco.
NAMESERVERS = ['1.1.1.1', '8.8.8.8', '9.9.9.9', '208.67.222.222']

# since you'll be asking a lot of DNS questions, use a set of (public) resolvers:
resolver = Resolver()
resolver.nameservers = NAMESERVERS


def compose_discover_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
    **kwargs
) -> Task:

    default_filter = {"is_dead": False, "not_resolvable": False}
    urls_filter = {**urls_filter, **default_filter}
    urls = Url.objects.all().filter(q_configurations_to_scan(level='url'), **urls_filter)
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter)

    if not urls:
        log.warning('Applied filters resulted in no urls. Cannot discover DNS endpoints without urls.')
        return group()

    urls = list(set(urls))

    tasks = []

    # Endpoint life cycle helps with keeping track of scan results over time. For internet.nl scans we create a few
    # 'fake' endpoints that are used to store scan results. The fake endpoints have a default port of 25, and ipv4
    # but these could be alternative ports and ipv6 as well. That is because the internet.nl scanner summarizes things
    # mostly on the url level.
    for url in urls:
        tasks.append(
            has_mx_without_cname.si(url)
            | connect_result.s(protocol="dns_mx_no_cname", url=url, port=0, ip_version=0)
            | has_soa.si(url)
            | connect_result.s(protocol="dns_soa", url=url, port=0, ip_version=0)
            | has_a_or_aaaa.si(url)
            | connect_result.s(protocol="dns_a_aaaa", url=url, port=0, ip_version=0)
        )

    return group(tasks)


def compose_verify_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
    **kwargs
) -> Task:

    default_filter = {"protocol__in": ["dns_mx_no_cname", "dns_soa", "dns_a_aaa"], "is_dead": False}
    endpoints_filter = {**endpoints_filter, **default_filter}
    endpoints = Endpoint.objects.all().filter(q_configurations_to_scan(level='endpoint'), **endpoints_filter)
    endpoints = endpoint_filters(endpoints, organizations_filter, urls_filter, endpoints_filter)

    tasks = []
    for endpoint in endpoints:
        tasks.append(
            has_mx_without_cname.si(endpoint.url)
            | connect_result.s(protocol="dns_mx_no_cname", url=endpoint.url, port=0, ip_version=0)
            | has_soa.si(endpoint.url)
            | connect_result.s(protocol="dns_soa", url=endpoint.url, port=0, ip_version=0)
            | has_a_or_aaaa.si(endpoint.url)
            | connect_result.s(protocol="dns_a_aaa", url=endpoint.url, port=0, ip_version=0)
        )
    return group(tasks)


@app.task(queue="storage")
def has_soa(url: Url):
    """
    The SOA records is the primary check for internet.nl mail. If there is a SOA
    record, you can run a mail scan. It's unclear at the time of writing why this is.
    This is used on internet.nl dashboard
    :param url:
    :return:
    """
    if get_dns_records(url, 'SOA'):
        return True
    return False


@app.task(queue="storage")
def has_mx_without_cname(url: Url) -> bool:
    """
    If there is an MX record, that is not part of a CNAME, store it as an mx_mail endpoint.
    This is a special endpoint that helps with the life-cycle of sending mail to this address.

    When asking a DNS server to give the MX record of a CNAME, it will do so, and give the MX of another
    domain on the url. That will give the impression you can send mail to it, but you can't.

    You'll see this behaviour on www cnames. As demonstrated below. This is common practice and probably a
    convenience result, as it points to the place that really contains the mx result.

    dig www.basisbeveiliging.nl mx

    ; <<>> DiG 9.10.6 <<>> www.basisbeveiliging.nl mx
    ;; global options: +cmd
    ;; Got answer:
    ;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 49917
    ;; flags: qr rd ra ad; QUERY: 1, ANSWER: 3, AUTHORITY: 0, ADDITIONAL: 1

    ;; OPT PSEUDOSECTION:
    ; EDNS: version: 0, flags:; udp: 512
    ;; QUESTION SECTION:
    ;www.basisbeveiliging.nl.	IN	MX

    ;; ANSWER SECTION:
    www.basisbeveiliging.nl. 21599	IN	CNAME	basisbeveiliging.nl.
    basisbeveiliging.nl.	299	IN	MX	20 mx2.forwardmx.io.
    basisbeveiliging.nl.	299	IN	MX	10 mx1.forwardmx.io.

    ;; Query time: 38 msec
    ;; SERVER: 8.8.8.8#53(8.8.8.8)
    ;; WHEN: Wed Mar 27 10:31:59 CET 2019
    ;; MSG SIZE  rcvd: 118

    """
    if get_dns_records(url, 'CNAME'):
        return False

    if get_dns_records(url, 'MX'):
        return True

    return False


@app.task(queue="storage")
def has_a_or_aaaa(url: Url) -> bool:
    """
    used for internet.nl web scans. The issue with regular endpoint is that you never know
    which one of the four exists. And it can also not be placed on a URL, as that would make url
    lifecycle harder. So we make an endpoint that signifies the existence of 'a website' regardless
    of protocol or port.
    :param url:
    :return:
    """
    if get_dns_records(url, 'A'):
        return True
    if get_dns_records(url, 'AAAA'):
        return True
    return False


@retry(wait=wait_exponential(multiplier=1, min=0, max=10),
       stop=stop_after_attempt(3), before=before_log(log, logging.DEBUG))
def get_dns_records(url, record_type):
    try:
        # a little delay to be friendly towards the server
        # this doesn't really help with parallel requests from the same server. Well, a little bit.
        sleep(0.03)
        return resolver.query(url.url, record_type)
    except NoAnswer:
        log.debug("The DNS response does not contain an answer to the question. %s %s " % (url.url, record_type))
        return None
    except NXDOMAIN:
        log.debug("dns query name does not exist. %s %s" % (url.url, record_type))
        return None
    except NoNameservers:
        log.debug("Pausing, or add more DNS servers...")
        sleep(20)


"""
# Given the mail server can be at any location, depending on the MX record, making a list of Mail servers AT
# a certain url doesn't add much value. Therefore below code is disabled.
# for ip_version in [4, 6]:
#     queue = "ipv4" if ip_version == 4 else "ipv6"
#     for port in [25, 587]:
#         for url in urls:
#             # MX also allows mailservers to run somewhere else. In that case there is an MX record,
#             # but no mailserver on that same address.
#             tasks.append(
#                 # This discovers if there is a mailserver running on the address. While helpful + a true endpoint
#                 # it is very much (and common) the case that mail is handled elsewhere. This is what the MX
#                 # record can state. Therefore there is not much value in just checking this.
#                 # todo: we should follow the MX value, instead of scanning the host directly.
#                 # Also: the MX value can have a series of failovers. So... now what?
#                 can_connect.si(protocol="smtp", url=url, port=port, ip_version=ip_version).set(queue=queue)
#                 | connect_result.s(protocol="smtp", url=url, port=port, ip_version=ip_version)
#             )
@app.task(queue="4and6", rate_limit='120/s')
def can_connect(protocol: str, url: Url, port: int, ip_version: int) -> bool:
    \"""
    Will try to connect to a mail server over a given port. Make sure the queue is set properly, so ipv6 is
    tested correctly too.

    todo: Important: sometimes you'll get an MX record back when there is no MX. This means the endpoint will be
    created but will not store scan results. Mail scans only occur if the MX is valid(?).

    Thus no endpoints will be created from this list:
    25/tcp  open  smtp
    587/tcp open  smtp
    465/tcp open  smtps

    receiving, not relevant
    106/tcp open  pop3pw
    110/tcp open  pop3
    143/tcp open  imap
    993/tcp open  imaps
    995/tcp open  pop3s

    \"""

    # The address that receives mail doesn't need an MX record. But does it _require_ a SOA record? Let's assume no.
    # If there are no MX records, then why try to connect at all?
    # Start of authority required for mail?
    # if not get_dns_records(url, 'SOA'):
    #     return False

    smtp = SMTP(timeout=5)
    log.debug('Checking if we can connect to the SMTP server on %s:%s' % (url.url, port))

    \"""
    From the docs:
    If the connect() call returns anything other than a success code, an SMTPConnectError is raised.

    Which is incorrect, there are at least 5 other exceptions that can occur when connecting.
    \"""
    try:
        smtp.connect(host=url.url, port=port)
        return True
    except SMTPConnectError:
        return False
    except (TimeoutError, socket.timeout, socket.gaierror):
        # socket.timeout: timed out = Specifying timeout.
        # socket.gaierror = [Errno 8] nodename nor servname provided, or not known
        return False
    except ConnectionRefusedError:
        # ConnectionRefusedError: [Errno 61] Connection refused
        return False
    except smtplib.SMTPServerDisconnected:
        # smtplib.SMTPServerDisconnected: Connection unexpectedly closed: timed out
        return False
"""
