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
from typing import List

from celery import Task, group
from dns.resolver import NXDOMAIN, NoAnswer, NoNameservers, Resolver, Timeout
from tenacity import before_log, retry, stop_after_attempt, wait_exponential

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners import plannedscan
from websecmap.scanners.models import Endpoint
from websecmap.scanners.plannedscan import retrieve_endpoints_from_urls
from websecmap.scanners.scanner.__init__ import (
    add_model_filter,
    endpoint_filters,
    q_configurations_to_scan,
    unique_and_random,
    url_filters,
)
from websecmap.scanners.scanner.http import connect_result
from websecmap.scanners.scanner.utils import get_nameservers

log = logging.getLogger(__name__)


def filter_discover(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
):

    default_filter = {"is_dead": False, "not_resolvable": False}
    urls_filter = {**urls_filter, **default_filter}
    urls = Url.objects.all().filter(q_configurations_to_scan(level="url"), **urls_filter).only("id", "url")
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter)
    urls = add_model_filter(urls, **kwargs)

    return unique_and_random(urls)


def filter_verify(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
):

    default_filter = {"protocol__in": ["dns_mx_no_cname", "dns_soa", "dns_a_aaaa"], "is_dead": False}
    endpoints_filter = {**endpoints_filter, **default_filter}
    endpoints = Endpoint.objects.all().filter(q_configurations_to_scan(level="endpoint"), **endpoints_filter)
    endpoints = endpoint_filters(endpoints, organizations_filter, urls_filter, endpoints_filter)
    endpoints = endpoints.only("id", "url__id", "url__url")

    endpoints = unique_and_random(endpoints)
    return unique_and_random([endpoint.url for endpoint in endpoints])


def compose_new_discover_task(urls: List[Url]):
    tasks = []

    # Endpoint life cycle helps with keeping track of scan results over time. For internet.nl scans we create a few
    # 'fake' endpoints that are used to store scan results. The fake endpoints have a default port of 25, and ipv4
    # but these could be alternative ports and ipv6 as well. That is because the internet.nl scanner summarizes things
    # mostly on the url level.
    for url in urls:
        tasks.append(
            has_mx_without_cname.si(url.url)
            | connect_result.s(protocol="dns_mx_no_cname", url_id=url.pk, port=0, ip_version=0)
            | has_soa.si(url.url)
            | connect_result.s(protocol="dns_soa", url_id=url.pk, port=0, ip_version=0)
            | has_a_or_aaaa.si(url.url)
            | connect_result.s(protocol="dns_a_aaaa", url_id=url.pk, port=0, ip_version=0)
            | plannedscan.finish.si("discover", "dns_endpoints", url.pk)
        )

    return group(tasks)


def compose_new_verify_task(urls):
    endpoints = retrieve_endpoints_from_urls(urls, protocols=["dns_mx_no_cname", "dns_soa", "dns_a_aaaa"])

    tasks = []
    for endpoint in endpoints:
        tasks.append(
            has_mx_without_cname.si(endpoint.url.url)
            | connect_result.s(protocol="dns_mx_no_cname", url_id=endpoint.url.pk, port=0, ip_version=0)
            | has_soa.si(endpoint.url.url)
            | connect_result.s(protocol="dns_soa", url_id=endpoint.url.pk, port=0, ip_version=0)
            | has_a_or_aaaa.si(endpoint.url.url)
            | connect_result.s(protocol="dns_a_aaaa", url_id=endpoint.url.pk, port=0, ip_version=0)
            | plannedscan.finish.si("verify", "dns_endpoints", endpoint.url.pk)
        )
    return group(tasks)


@app.task(queue="storage")
def plan_discover(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
):
    urls = filter_discover(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    plannedscan.request(activity="discover", scanner="dns_endpoints", urls=urls)


@app.task(queue="storage")
def plan_verify(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
):

    urls = filter_verify(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    plannedscan.request(activity="verify", scanner="dns_endpoints", urls=urls)


@app.task(queue="storage")
def compose_planned_verify_task(**kwargs):
    urls = plannedscan.pickup(activity="verify", scanner="dns_endpoints", amount=kwargs.get("amount", 25))
    return compose_new_verify_task(urls)


@app.task(queue="storage")
def compose_planned_discover_task(**kwargs):
    urls = plannedscan.pickup(activity="discover", scanner="dns_endpoints", amount=kwargs.get("amount", 25))
    return compose_new_discover_task(urls)


def compose_manual_verify_task(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
) -> Task:

    urls = filter_verify(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    return compose_new_verify_task(urls)


def compose_manual_discover_task(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
) -> Task:
    urls = filter_discover(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    return compose_new_discover_task(urls)


def compose_discover_task(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
) -> Task:
    # this method is here for backwards compatibility in the internet.nl dashboard

    urls = filter_discover(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    return compose_new_discover_task(urls)


def compose_verify_task(
    organizations_filter: dict = dict(), urls_filter: dict = dict(), endpoints_filter: dict = dict(), **kwargs
) -> Task:
    # this method is here for backwards compatibility in the internet.nl dashboard

    urls = filter_verify(organizations_filter, urls_filter, endpoints_filter, **kwargs)
    return compose_new_verify_task(urls)


@app.task(queue="storage")
def has_soa(url: str):
    """
    The SOA records is the primary check for internet.nl mail. If there is a SOA
    record, you can run a mail scan. It's unclear at the time of writing why this is.
    This is used on internet.nl dashboard

    internet.nl uses unbound do perform this check, which is very heavy and does a lot of things probably
    a lot cleaner and better. The build instructions are here:
    https://github.com/NLnetLabs/Internet.nl/blob/5f56202848e7a71d1a7dd8204d39b8f1246bbe34/docker/Dockerfile

    But still, since the queries are so simple, we prefer not to use it.

    In "https://github.com/NLnetLabs/Internet.nl/blob/cece8255ac7f39bded137f67c94a10748970c3c7/checks/views/shared.py"
    we see get_valid_domain_mai using unbound with RR_TYPE_SOA. This means not only SOA on the current subdomain,
    but getting ANY soa record back is fine.

    The domain itself does not need to be authoritive for them. Which means basically scan everything.
    Can we find a domain that does not have a SOA record?

    This is OK;  casdasdasdvdr.overheid.nl  as dig  casdasdasdvdr.overheid.nl SOA returns overheid.nl as one of it's
    results.

    asdkansdkansdkl.blockchainpilots.nl is not ok. as it has only the nl. in authority section.

    Is there an option in dnspython's resolver.query that might emulate this behavior?
    We can't blindly use the parents domain, as that is not how DNS works :)

    We're simulating:
    cb_data = ub_resolve_with_timeout(
        dname, unbound.RR_TYPE_SOA, unbound.RR_CLASS_IN, timeout)

    in DNSPython:
    def query(qname, rdtype=dns.rdatatype.A, rdclass=dns.rdataclass.IN,
          tcp=False, source=None, raise_on_no_answer=True,
          source_port=0, lifetime=None):

    Comparison:

                    unbound                 | dnspython
    domain_name |   dname                   | qname
    type:       |   unbound.RR_TYPE_SOA     |  "SOA" (could differ)
    rdclass:    |   unbound.RR_CLASS_IN     | dns.rdataclass.IN (default)

    Our best bet is that "SOA" is not the same as RR_TYPE_SOA, or dns.rdatatype.SOA... so let's try that.
    dns.rdatatype.SOA and "SOA" deliver the same result: it does not exist. So why does it exist on internet.nl?

    internet.nl does use get_valid_domain_mail to validate and perform the resolving function...
    https://github.com/NLnetLabs/Internet.nl/blob/9f0cfb5baffbe76b4e28cda297093b0e0aef8fae/checks/batch/util.py

    The difference in internet.nl is dat the resolve DOES get something back, even if its not a SOA...

    "
    def get_valid_domain_mail(mailaddr, timeout=5):
    dname = validate_dname(mailaddr)
    if dname is None:
        return None

    cb_data = ub_resolve_with_timeout(
        dname, unbound.RR_TYPE_SOA, unbound.RR_CLASS_IN, timeout)

    if cb_data.get("nxdomain") and cb_data["nxdomain"]:
        return None

    return dname
    "

    If we look at vars((resolver.query("data.overheid.nl", "SOA", raise_on_no_answer=False).response))
    then we see there is an authority section. Since unbound is a recursive dns resolver, it might just attempt
    to retrieve the answer from the authority.

    In this example we see that this is happening, and the NXdomain check is also performed. Thus the
    recursivity is the actual thing that differs.
    https://stackoverflow.com/questions/4066614/how-can-i-find-the-authoritative-dns-server-for-a-domain-using-dnspython

    Of course, we're not going to write recursive code, as this is a very common problem, and a solution
    is likely waiting for us.

    Internet.nl uses this specific version of unbound:
    https://github.com/ralphdolmans/unbound/blob/internetnl/README.md

    The real difference it seems is that we do accept "no answer", but do not accept "nxdomain" issues. We can
    also see this when looking at get_valid_domain_web, that seems to really look at the data.

    Test it like this:
    from websecmap.organizations.models import Url
    from websecmap.scanners.scanner import dns_endpoints
    dns_endpoints.has_soa(Url(url="www.arnhem.nl"))

    The answer returned does not evaluate as True or False.

    So the check is not really 'IF' there is a SOA record, because there is not at data.overheid.nl. But
    that you get an answer, and any answer is basically fine.

    :param url:
    :return:
    """

    answer = get_dns_records_accepting_no_answer(url, "SOA")
    if answer is None:
        return False

    if answer is False:
        return False

    if answer.response:
        return True

    # fail safely for all other edge cases that might exist.
    return False


@app.task(queue="storage")
def has_mx_without_cname(url: str) -> bool:
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
    ;www.basisbeveiliging.nl.   IN  MX

    ;; ANSWER SECTION:
    www.basisbeveiliging.nl. 21599  IN  CNAME   basisbeveiliging.nl.
    basisbeveiliging.nl.    299 IN  MX  20 mx2.forwardmx.io.
    basisbeveiliging.nl.    299 IN  MX  10 mx1.forwardmx.io.

    ;; Query time: 38 msec
    ;; SERVER: 8.8.8.8#53(8.8.8.8)
    ;; WHEN: Wed Mar 27 10:31:59 CET 2019
    ;; MSG SIZE  rcvd: 118

    """
    if get_dns_records(url, "CNAME"):
        return False

    if get_dns_records(url, "MX"):
        return True

    return False


@app.task(queue="storage")
def has_a_or_aaaa(url: str) -> bool:
    """
    used for internet.nl web scans. The issue with regular endpoint is that you never know
    which one of the four exists. And it can also not be placed on a URL, as that would make url
    lifecycle harder. So we make an endpoint that signifies the existence of 'a website' regardless
    of protocol or port.
    :param url:
    :return:
    """
    if get_dns_records(url, "A"):
        return True
    if get_dns_records(url, "AAAA"):
        return True
    return False


@retry(
    wait=wait_exponential(multiplier=1, min=0, max=10),
    stop=stop_after_attempt(3),
    before=before_log(log, logging.DEBUG),
)
def get_dns_records(url: str, record_type):
    resolver = Resolver()
    resolver.nameservers = get_nameservers()

    try:
        # a little delay to be friendly towards the server
        # this doesn't really help with parallel requests from the same server. Well, a little bit.
        sleep(0.03)
        return resolver.query(url, record_type)
    except NoAnswer:
        log.debug("The DNS response does not contain an answer to the question. %s %s " % (url, record_type))
        return None
    except NXDOMAIN:
        log.debug("dns query name does not exist. %s %s" % (url, record_type))
        return None
    except NoNameservers:
        log.debug("Pausing, or add more DNS servers...")
        sleep(20)
    except Timeout:
        # some DNS server queries result in a timeout for things that do not exist. This takes 30 seconds.
        log.debug(f"Timeout received for DNS query to {url}.")
        return False


@retry(
    wait=wait_exponential(multiplier=1, min=0, max=10),
    stop=stop_after_attempt(3),
    before=before_log(log, logging.DEBUG),
)
def get_dns_records_accepting_no_answer(url: str, record_type):
    resolver = Resolver()
    resolver.nameservers = get_nameservers()

    try:
        # a little delay to be friendly towards the server
        # this doesn't really help with parallel requests from the same server. Well, a little bit.
        sleep(0.03)
        answer = resolver.query(url, record_type, raise_on_no_answer=False)
        log.debug("dns query returned an answer %s %s" % (url, record_type))
        return answer
    except NoAnswer:
        # this will never happen, as we explicitly say OK. This means that only domains that really
        # do not return ANY answer *where NXDOMAIN is returned* will be false.
        return None
    except NXDOMAIN:
        log.debug("dns query name does not exist. %s %s" % (url, record_type))
        return None
    except NoNameservers:
        log.debug("Pausing, or add more DNS servers...")
        sleep(20)
    except Timeout:
        # some DNS server queries result in a timeout for things that do not exist. This takes 30 seconds.
        log.debug(f"Timeout received for DNS query to {url}.")
        return False


"""
# This has been removed because the approach taken is not feasable or relevant for mail.
# It is still here to learn from it.
#
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
