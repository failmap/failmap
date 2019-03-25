"""
Scans using internet.nl API.
Docs: https://batch.internet.nl/api/batch/documentation/

The Internet.nl scanner scans for a lot of things at the same time. We scan all those results, even though we might not
display them all. It might mean that some scans have a relationsship with each other.

This scanner focusses on the availability and implementation of SPF, DKIM, DMARC, DNSSEC and STARTTLS.

A scan is run in a batch of maximum 5000 urls. A batch request is made and then stored. A periodic task checks if there
are updates to the scan. If so, the updates are processed and on a good day the scan is closed and saved.

Since the result url stays valid for a while, you can port it to another server without costing more resources on i.nl.

A batch scan will take at least 30 minutes and can last days. Please don't add too much scans, as you'll get kicked.

To know what domains we need to scan, it's possible to search for domains with MX records using 'failmap discover mail'.
This optimization saves about 80% of resources, which is a whole lot.

Given this scanner is slow, we cannot add this to the onboarding routine unfortunately.

Todo:
[X] Store API username
[X] Store API password
[X] Request a scan
[X] Read a scan status
[X] Return the scan results
[X] Store the scan results
[X] Run a dig on a subdomain for MX records. If MX, then add to scan. If not, how do you delete / invalidate the scans?
[X] Schedule a scan request every 7 days
[X] Add MX records every 5 days
[X] Schedule the update task every 30 minutes
[ ] Create reports and relationships of findings. Also determine severity etc.
[ ] Handle NO MX return messages, do not save those scans and remove the capability... what happens with the last
    scan result....????

Commands:
# Search for MX records
failmap discover mail -o Zutphen

# scan the quality of the mail of an organization, only registers a scan
failmap scan mail -o Zutphen

# request the status of a scan, can finish the scan when ready
failmap internetnl_status_update

You can load up this file in ipython and run test_store() if needed.
"""

import logging
import smtplib
import socket
import uuid
from datetime import datetime
from smtplib import SMTP, SMTPConnectError
from time import sleep
from typing import List

import pytz
import requests
from celery import Task, group
from constance import config
from dns.resolver import NXDOMAIN, NoAnswer, NoNameservers, Resolver
from requests.auth import HTTPBasicAuth
from tenacity import before_log, retry, stop_after_attempt, wait_exponential

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, InternetNLScan
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.http import connect_result
from websecmap.scanners.scanner.scanner import (allowed_to_scan, endpoint_filters,
                                                q_configurations_to_scan, url_filters)

log = logging.getLogger(__name__)


API_URL_MAIL = "https://batch.internet.nl/api/batch/v1.0/mail/"
MAX_INTERNET_NL_SCANS = 5000

NAMESERVERS = ['1.1.1.1', '8.8.8.8', '9.9.9.9', '208.67.222.222']

# since you'll be asking a lot of DNS questions, use a set of resolvers:
resolver = Resolver()
# cloudflare, google, quad9, cisco.
resolver.nameservers = NAMESERVERS


# while internet.nl scans on port 25
# (see https://github.com/NLnetLabs/Internet.nl/blob/f003365b1d560bdfbb5bd772d735a41696277639/checks/tasks/tls.py)
# we will see if SMTP works on both standard ports.


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
    **kwargs
) -> Task:

    if not allowed_to_scan("internet_nl_mail"):
        return group()

    default_filter = {"is_dead": False, "not_resolvable": False}
    urls_filter = {**urls_filter, **default_filter}
    urls = Url.objects.all().filter(q_configurations_to_scan(level='url'), **urls_filter)

    endpoints_filter = {'is_dead': False, "protocol": 'mx_mail'}
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter)

    if not urls:
        log.warning('Applied filters resulted in no urls, thus no mail scan tasks!')
        return group()

    urls = list(set(urls))

    # do all in one. Throw exception at more than 5000.
    if len(urls) >= MAX_INTERNET_NL_SCANS:
        raise ValueError("Attempting to scan more than 5000 urls on internet.nl, which is above the daily limit. "
                         "Slice your scan requests to be at maximum 5000 urls per day.")

    log.info('Creating internetnl mail scan task for %s urls.', len(urls))

    return group([register_scan.si(urls, config.INTERNET_NL_API_USERNAME, config.INTERNET_NL_API_PASSWORD, 'mail',
                                   API_URL_MAIL)])


def compose_discover_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
    **kwargs
) -> Task:
    """
    Tries each URL to determine if there is a matching MX record. If so, this is stored.

    Warning: this scanner does NOT try to create mail server endpoints.
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

    :return:
    """

    if not allowed_to_scan("internet_nl_mail"):
        return group()

    default_filter = {"is_dead": False, "not_resolvable": False}
    urls_filter = {**urls_filter, **default_filter}
    urls = Url.objects.all().filter(q_configurations_to_scan(level='url'), **urls_filter)
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter)

    if not urls:
        log.warning('Applied filters resulted in no urls, thus no mail MX discover tasks!')
        return group()

    urls = list(set(urls))

    tasks = []

    # Endpoint life cycle helps with keeping track of scan results over time. For internet.nl scans we create a few
    # 'fake' endpoints that are used to store scan results. The fake endpoints have a default port of 25, and ipv4
    # but these could be alternative ports and ipv6 as well. That is because the internet.nl scanner summarizes things
    # mostly on the url level.
    for url in urls:
        tasks.append(
            # If there is an MX record, that is not part of a CNAME, store it as an mx_mail endpoint.
            # This is a special endpoint that helps with the life-cycle of sending mail to this address.
            discover_mx_records.si(url)
            | connect_result.s(protocol="mx_mail", url=url, port=25, ip_version=4)

            # The same goes for SOA records, which is now the primary check for internet.nl If there is a SOA
            # record, you can run a mail scan. It's unclear at the time of writing why this is.
            | discover_soa_record.si(url)
            | connect_result.s(protocol="soa_mail", url=url, port=25, ip_version=4)
        )

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

    if not allowed_to_scan("internet_nl_mail"):
        return group()

    default_filter = {"protocol__in": ["smtp", "smtps"], "is_dead": False}
    endpoints_filter = {**endpoints_filter, **default_filter}
    endpoints = Endpoint.objects.all().filter(q_configurations_to_scan(level='endpoint'), **endpoints_filter)
    endpoints = endpoint_filters(endpoints, organizations_filter, urls_filter, endpoints_filter)

    tasks = []
    for endpoint in endpoints:

        tasks.append(
            discover_mx_records.si(endpoint.url)
            | connect_result.s(protocol="mx_mail", url=endpoint.url, port=25, ip_version=4)
            | discover_soa_record.si(endpoint.url)
            | connect_result.s(protocol="soa_mail", url=endpoint.url, port=25, ip_version=4)
        )

        # Just like above, we don't need to verify this.
        # queue = "ipv4" if endpoint.ip_version == 4 else "ipv6"
        # tasks.append(can_connect.si(protocol=endpoint.protocol, url=endpoint.url,
        #                             port=endpoint.port, ip_version=endpoint.ip_version).set(queue=queue)
        #              | connect_result.s(protocol=endpoint.protocol, url=endpoint.url,
        #                                 port=endpoint.port, ip_version=endpoint.ip_version))
    return group(tasks)


@app.task(queue="4and6", rate_limit='120/s')
def can_connect(protocol: str, url: Url, port: int, ip_version: int) -> bool:
    """
    Will try to connect to a mail server over a given port. Make sure the queue is set properly, so ipv6 is
    tested correctly too.

    todo: Important: sometimes you'll get an MX record back when there is no MX. This means the endpoint will be
    created but will not store scan results. Mail scans only occur if the MX is valid(?).
    """

    # The address that receives mail doesn't need an MX record. But does it _require_ a SOA record? Let's assume no.
    # If there are no MX records, then why try to connect at all?
    # Start of authority required for mail?
    # if not get_dns_records(url, 'SOA'):
    #     return False

    smtp = SMTP(timeout=5)
    log.debug('Checking if we can connect to the SMTP server on %s:%s' % (url.url, port))

    """
    From the docs:
    If the connect() call returns anything other than a success code, an SMTPConnectError is raised.

    Which is incorrect, there are at least 5 other exceptions that can occur when connecting.
    """
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


# this should be a more generic DNS log.
@app.task(queue="storage")
def discover_mx_records(url: Url):

    if has_mx_records(url):
        return True
    else:
        return False


@app.task(queue="storage")
def discover_soa_record(url: Url):
    if get_dns_records(url, 'SOA'):
        return True
    return False


def has_mx_records(url: Url) -> bool:
    # todo: can we check if the mail is routed outside of the country somehow? Due to privacy concerns / GDPR?

    log.debug('Checking for MX at %s' % url)
    # a little delay to be friendly towards the server
    sleep(0.03)

    cname_records = get_dns_records(url, 'CNAME')

    if cname_records:
        log.debug("-- %s is a CNAME and might give problems with DKIM." % url)
        return False

    mx_records = get_dns_records(url, 'MX')
    if mx_records:
        log.debug("!! %s MX Found. Exchange: %s" % (url, mx_records[0].exchange))
        return True

    return False


@retry(wait=wait_exponential(multiplier=1, min=0, max=10),
       stop=stop_after_attempt(3), before=before_log(log, logging.DEBUG))
def get_dns_records(url, record_type):
    try:
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


@app.task(queue='storage')
def check_running_scans(store_as_protocol: str = 'mx_mail'):
    """
    Gets status on all running scans from internet, and try to handle/finish the scan when possible.

    This is not a task for Celery exponential backoffs, for the simple reason a scan can take a day or two and the queue
    might reset and stuff. Also someone might want to copy the result urls into other systems.

    :return: None
    """

    unfinished_scans = InternetNLScan.objects.all().filter(finished=False)
    for scan in unfinished_scans:
        # poll the url for updates.
        """
        Retrieving the status is a simple get request

        GET /api/batch/v1.0/results/01c70c7972d143ffb0c5b45d5b8116cb/ HTTP/1.1
        """
        try:
            response = requests.get(
                scan.status_url,
                auth=HTTPBasicAuth(config.INTERNET_NL_API_USERNAME, config.INTERNET_NL_API_PASSWORD),
                # a massive timeout for a large file.
                timeout=(300, 300)
            )
            response = response.json()
        except requests.exceptions.ConnectionError:
            log.exception("Could not connect to batch.internet.nl")
            return

        """
        Some status messages you can expect:
            "message": "Batch request is registering domains",
            "message": "Batch request is running",
            "message": "Results are being generated",
        """
        scan.message = response['message']
        log.debug("Scan %s: %s" % (scan.pk, response['message']))

        if response['message'] == "OK":
            log.debug("Hooray, a scan has finished.")
            scan.finished = True
            scan.finished_on = datetime.now(pytz.utc)
            scan.success = True
            log.debug("Going to process the scan results.")

            store(response, internet_nl_scan_type=scan.type, protocol=store_as_protocol)

        if response['message'] in ["Error while registering the domains" or "Problem parsing domains"]:
            log.debug("Scan encountered an error.")
            scan.finished = True
            scan.finished_on = datetime.now(pytz.utc)

        scan.save()

    return None


@app.task(queue="storage")
def register_scan(urls: List[Url], username, password, internet_nl_scan_type: str = 'mail', api_url: str = ""):
    """
    This registers a scan and results the URL where the scan results can be found later on.

    :param urls:
    :param username:
    :param password:
    :return:
    """

    """
    Register scan request:
    POST /api/batch/v1.0/web/ HTTP/1.1
    {
        "name": "My web test",
        "domains": ["nlnetlabs.nl", "www.nlnetlabs.nl", "opennetlabs.nl", "www.opennetlabs.nl"]
    }
    """
    scan_id = str(uuid.uuid4())
    urls = [url.url for url in urls]
    data = {"name": "Web Security Map Scan %s" % scan_id, "domains": urls}
    answer = requests.post(api_url, json=data, auth=HTTPBasicAuth(username, password), timeout=(300, 300))
    log.debug("Received answer from internet.nl: %s" % answer.content)

    answer = answer.json()

    check_correct_user(answer)
    check_api_version(answer)

    """
    Expected answer:
    HTTP/1.1 200 OK
    Content-Type: application/json
    {
        "success": true,
        "message": "OK",
        "data": {
            "results": "https://batch.internet.nl/api/batch/v1.0/results/01c70c7972d143ffb0c5b45d5b8116cb/"
        }
    }
    """
    status_url = get_status_url(answer)
    log.debug('Received scan status url: %s' % status_url)

    scan = InternetNLScan()
    scan.started_on = datetime.now(pytz.utc)
    scan.started = True
    scan.status_url = status_url
    scan.message = answer
    scan.type = internet_nl_scan_type

    scan.save()

    return scan


def check_correct_user(answer):
    # handle an unknown user error:
    if answer.get("message", None) == "Unknown user":
        raise AttributeError("Unknown user. Did you configure your internet.nl username and password?")


def check_api_version(answer):
    # handle API upgrades
    if answer.get("message", None) == "Make sure you are using a valid URL with the current batch API version (1.0)":
        raise AttributeError("API Changed. Review the documentation at "
                             "batch.internet.nl using your internet.nl credentials")


def get_status_url(answer):
    status_url = answer.get('data', {}).get('results', "")
    if not status_url:
        raise AttributeError("Could not get scanning status url. Response from server: %s" % answer)

    return status_url


@app.task(queue='storage')
def store(result: dict, internet_nl_scan_type: str = 'mail', protocol='mx_mail'):
    # todo: it's not clear what the answer is if there is no MX record / no mail server defined. What is the score then?
    # relevant since MX might point to nothing or is removed meanwhile.
    """
    :param result: json blob from internet.nl
    :param internet_nl_scan_type: web or mail
    :param protocol: what endpoint protocol to select, defaults to mx_mail, can also be soa_mail.
    :param urls: list of urls in failmap database
    :param internet_nl_scan_type: mail or web
    """

    domains = result.get('data', {}).get('domains', {})
    if not domains:
        raise AttributeError("Domains missing from scan results. What's going on?")

    for domain in domains:

        log.debug(domain)

        if domain['status'] != "ok":
            log.debug("%s scan failed on %s" % (internet_nl_scan_type, domain['domain']))
            continue

        # try to match the endpoint. Internet nl scans target port 25 and ipv4 primarily.
        endpoint = Endpoint.objects.all().filter(protocol=protocol, port=25,
                                                 url__url=domain['domain'],
                                                 is_dead=False, ip_version=4).first()

        if not endpoint:
            log.debug("No matching endpoint found, perhaps this was deleted / resolvable meanwhile. Skipping")
            continue

        # link changes every time, so can't save that as message.
        store_endpoint_scan_result(
            scan_type='internet_nl_%s_overall_score' % internet_nl_scan_type,
            endpoint=endpoint,
            rating=domain['score'],
            message='ok',
            evidence=domain['link']
        )

        # startls, dane etc.
        for category in domain['categories']:
            scan_type = 'internet_nl_%s_%s' % (internet_nl_scan_type, category['category'])
            store_endpoint_scan_result(
                scan_type=scan_type,
                endpoint=endpoint,
                rating=category['passed'],
                message='',
                evidence=domain['link']
            )

        # tons of specific views and scan values that might be valuable to report on. Save all of them.
        for view in domain['views']:
            scan_type = 'internet_nl_%s' % view['name']
            store_endpoint_scan_result(
                scan_type=scan_type,
                endpoint=endpoint,
                rating=view['result'],
                message='',
                evidence=domain['link']
            )
