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
import uuid
from datetime import datetime
from time import sleep
from typing import List

import pytz
import requests
from celery import Task, group
from constance import config
from dns.resolver import NXDOMAIN, NoAnswer, NoNameservers, Resolver
from requests.auth import HTTPBasicAuth

from failmap.celery import app
from failmap.organizations.models import Url
from failmap.scanners.models import InternetNLScan, UrlGenericScan
from failmap.scanners.scanmanager.url_scan_manager import UrlScanManager
from failmap.scanners.scanner.scanner import allowed_to_scan, q_configurations_to_scan, url_filters

log = logging.getLogger(__name__)


API_URL_MAIL = "https://batch.internet.nl/api/batch/v1.0/mail/"
MAX_INTERNET_NL_SCANS = 5000


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
    **kwargs
) -> Task:

    if not allowed_to_scan("scanner_mail_internet_nl"):
        return group()

    default_filter = {"is_dead": False, "not_resolvable": False, "dns_supports_mx": True}
    urls_filter = {**urls_filter, **default_filter}
    urls = Url.objects.all().filter(q_configurations_to_scan(level='url'), **urls_filter)
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

    return group([register_scan.si(urls, config.INTERNET_NL_API_USERNAME, config.INTERNET_NL_API_PASSWORD)])


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
    106/tcp open  pop3pw
    110/tcp open  pop3
    143/tcp open  imap
    465/tcp open  smtps
    993/tcp open  imaps
    995/tcp open  pop3s

    :return:
    """

    if not allowed_to_scan("scanner_mail_internet_nl"):
        return group()

    default_filter = {"is_dead": False, "not_resolvable": False}
    urls_filter = {**urls_filter, **default_filter}
    urls = Url.objects.all().filter(q_configurations_to_scan(level='url'), **urls_filter)
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter)

    if not urls:
        log.warning('Applied filters resulted in no urls, thus no mail MX discover tasks!')
        return group()

    urls = list(set(urls))
    task = discover_mx_records.si(urls)
    return group(task)


@app.task(queue="storage")
def discover_mx_records(urls: List[Url]):
    urls_with_mx = find_mx_records(urls)

    log.debug("Found %s urls with MX record." % len(list(urls_with_mx)))

    for url in urls_with_mx:
        url.dns_supports_mx = True
        url.save(update_fields=['dns_supports_mx'])

    # clean up removed mailservers, saved as "no mx"
    urls_without_mx = list(set(urls) - set(urls_with_mx))

    clean_urls_without_mx(urls_without_mx)


def find_mx_records(urls: List[Url]):
    # todo: can we check if the mail is routed outside of the country somehow? Due to privacy concerns / GDPR?

    has_mx = []

    # since you'll be asking a lot of DNS questions, use a set of resolvers:
    resolver = Resolver()
    # cloudflare, google, quad9, cisco.
    resolver.nameservers = ['1.1.1.1', '8.8.8.8', '9.9.9.9', '208.67.222.222']

    for url in urls:
        # a little delay to be friendly towards the server
        sleep(0.03)

        try:
            records = resolver.query(url.url, 'MX')
            if records:
                # use visual markers to quickly see if this test works.
                log.debug("!! %s MX Found. Exchange: %s" % (url, records[0].exchange))
                has_mx.append(url)
        except NoAnswer:
            log.debug("   %s has no MX record, skipping." % url)
        except NXDOMAIN as e:
            log.debug("EX %s resulted in error: %s, skipping" % (url, str(e)))
        except NoNameservers as e:
            # Too many iterations will cause an error to return and to return more often.
            log.debug("EX %s Name server did not accept any more queries. Are you asking too much? %s" % (url, str(e)))
            log.debug("Pausing, or add more DNS servers...")
            urls.append(url)
            sleep(20)

    return has_mx


def clean_urls_without_mx(urls: List[Url]):
    # There are often MANY urls that don't have an MX. Update those.

    # We're doing this using iteration because an IN query with 1000's of id's
    # will trigger OperationalError too many SQL variables.

    # We're not still doing IN queries with chunked urls, because that's ugly and complex.

    for url in urls:
        obsolete_scans = UrlGenericScan.objects.all().filter(
            is_the_latest_scan=True,
            type__startswith='internet_nl_mail_',
            url=url
        )

        # log.debug("Found %s obsolete scans for this url %s." % (len(list(obsolete_scans)), url))

        for obsolete_scan in obsolete_scans:
            UrlScanManager.add_scan(
                scan_type=obsolete_scan.type,
                url=obsolete_scan.url,
                rating="mx removed",
                message="MX record removed, not possible to send mail to this url anymore."
            )

    log.debug("Cleaned obsolete scans.")


@app.task(queue='storage')
def check_running_scans():
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
            store(response)

        if response['message'] in ["Error while registering the domains" or "Problem parsing domains"]:
            log.debug("Scan encountered an error.")
            scan.finished = True
            scan.finished_on = datetime.now(pytz.utc)

        scan.save()

    return None


@app.task(queue="storage")
def register_scan(urls: List[Url], username, password):
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
    data = {"name": "Failmap Scan %s" % scan_id, "domains": urls}
    answer = requests.post(API_URL_MAIL, json=data, auth=HTTPBasicAuth(username, password), timeout=(300, 300))
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
    scan.type = "mail"
    # todo: do we need to add a list of urls or something like that for debugging purposes?

    scan.save()

    return status_url


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


def test_store():
    # The result from the documentation can be ignored, it's not up to date anymore.
    # this result is from a real scan
    result = {
        "message": "OK",
        "data": {
            "name": "Failmap Scan 9b33a48d-3507-422d-b520-974a0bcdbcd8",
            "submission-date": "2018-11-22T09:45:07.274815+00:00",
            "api-version": "1.0",
            "domains": [
                {
                    "status": "ok",
                    "domain": "arnhem.nl",
                    "views": [
                        {
                            "result": True,
                            "name": "mail_starttls_cert_domain"
                        },
                        {
                            "result": True,
                            "name": "mail_starttls_tls_version"
                        },
                        {
                            "result": True,
                            "name": "mail_starttls_cert_chain"
                        },
                        {
                            "result": True,
                            "name": "mail_starttls_tls_available"
                        },
                        {
                            "result": True,
                            "name": "mail_starttls_tls_clientreneg"
                        },
                        {
                            "result": True,
                            "name": "mail_starttls_tls_ciphers"
                        },
                        {
                            "result": False,
                            "name": "mail_starttls_dane_valid"
                        },
                        {
                            "result": False,
                            "name": "mail_starttls_dane_exist"
                        },
                        {
                            "result": True,
                            "name": "mail_starttls_tls_secreneg"
                        },
                        {
                            "result": False,
                            "name": "mail_starttls_dane_rollover"
                        },
                        {
                            "result": True,
                            "name": "mail_starttls_cert_pubkey"
                        },
                        {
                            "result": True,
                            "name": "mail_starttls_cert_sig"
                        },
                        {
                            "result": True,
                            "name": "mail_starttls_tls_compress"
                        },
                        {
                            "result": False,
                            "name": "mail_starttls_tls_keyexchange"
                        },
                        {
                            "result": False,
                            "name": "mail_auth_dmarc_policy"
                        },
                        {
                            "result": True,
                            "name": "mail_auth_dmarc_exist"
                        },
                        {
                            "result": True,
                            "name": "mail_auth_spf_policy"
                        },
                        {
                            "result": True,
                            "name": "mail_auth_dkim_exist"
                        },
                        {
                            "result": True,
                            "name": "mail_auth_spf_exist"
                        },
                        {
                            "result": True,
                            "name": "mail_dnssec_mailto_exist"
                        },
                        {
                            "result": True,
                            "name": "mail_dnssec_mailto_valid"
                        },
                        {
                            "result": True,
                            "name": "mail_dnssec_mx_valid"
                        },
                        {
                            "result": True,
                            "name": "mail_dnssec_mx_exist"
                        },
                        {
                            "result": False,
                            "name": "mail_ipv6_mx_address"
                        },
                        {
                            "result": False,
                            "name": "mail_ipv6_mx_reach"
                        },
                        {
                            "result": True,
                            "name": "mail_ipv6_ns_reach"
                        },
                        {
                            "result": True,
                            "name": "mail_ipv6_ns_address"
                        }
                    ],
                    "score": 77,
                    "link": "https://batch.internet.nl/mail/arnhem.nl/223685/",
                    "categories": [
                        {
                            "category": "ipv6",
                            "passed": False
                        },
                        {
                            "category": "dnssec",
                            "passed": True
                        },
                        {
                            "category": "auth",
                            "passed": False
                        },
                        {
                            "category": "tls",
                            "passed": False
                        }
                    ]
                }
            ],
            "finished-date": "2018-11-22T09:55:56.103073+00:00",
            "identifier": "e5ea54ede6ce42f5a20fad6d0b049d89"
        },
        "success": True
    }

    store(result)


@app.task(queue='storage')
def store(result: dict):
    # todo: it's not clear what the answer is if there is no MX record / no mail server defined. What is the score then?
    # relevant since MX might point to nothing or is removed meanwhile.
    """
    :param result: json blob from internet.nl
    :param urls: list of urls in failmap database
    """

    domains = result.get('data', {}).get('domains', {})
    if not domains:
        raise AttributeError("Domains missing from scan results. What's going on?")

    for domain in domains:

        log.debug(domain)

        if domain['status'] != "ok":
            log.debug("Mail scan failed on %s" % domain['domain'])
            continue

        # try to match the url
        url = Url.objects.all().filter(
            is_dead=False,
            not_resolvable=False,
            url=domain['domain']).first()

        if not url:
            log.debug("No matching URL found, perhaps this was deleted / resolvable meanwhile. Skipping")
            continue

        # link changes every time, so can't save that as message.
        UrlScanManager.add_scan(
            scan_type='internet_nl_mail_overall_score',
            url=url,
            rating=domain['score'],
            message='ok',
            evidence=domain['link']
        )

        # startls, dane etc.
        for category in domain['categories']:
            scan_type = 'internet_nl_mail_%s' % category['category']
            UrlScanManager.add_scan(
                scan_type=scan_type,
                url=url,
                rating=category['passed'],
                message='',
                evidence=domain['link']
            )

        # tons of specific views and scan values that might be valuable to report on. Save all of them.
        for view in domain['views']:
            scan_type = 'internet_nl_%s' % view['name']
            UrlScanManager.add_scan(
                scan_type=scan_type,
                url=url,
                rating=view['result'],
                message='',
                evidence=domain['link']
            )
