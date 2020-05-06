"""
Web Security Map implementation of internet.nl scans.
"""
import hashlib
import json
import logging
from datetime import datetime
from typing import List, Tuple

import pytz
from celery import Task, group
from constance import config
from django.db import transaction
import tldextract
import ipaddress

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, InternetNLV2Scan, InternetNLV2StateLog
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.internet_nl_v2 import (InternetNLApiSettings, register, result,
                                                       status)

log = logging.getLogger(__name__)


def valid_api_settings(scan: InternetNLV2Scan):
    if not config.INTERNET_NL_API_USERNAME:
        update_state(scan, "error", "Username for internet.nl scan not configured. Configure the username in the "
                                    "settings on the admin page.")
        return False

    if not config.INTERNET_NL_API_PASSWORD:
        update_state(scan, "error", "Password for internet.nl scan not configured. Configure the username in the "
                                    "settings on the admin page.")
        return False

    if not config.INTERNET_NL_API_URL:
        update_state(scan, "error", "No url supplied for internet.nl scans. The url can be configured in the "
                                    "settings on the admin page.")
        return False

    # validate the url itself:
    extract = tldextract.extract(config.INTERNET_NL_API_URL)
    if not extract.suffix:
        # can can still be an IP address, which should work too
        try:
            ipaddress.ip_address(extract.domain)
        except ValueError:
            update_state(scan, "error", "The internet.nl api url is not a valid url or IP format. Always start with "
                                        "https:// and then the address.")

    if not config.INTERNET_NL_MAXIMUM_URLS:
        update_state(scan, "error", "No maximum supplied for the amount of urls in an internet.nl scans. "
                                    "This can be configured in the settings on the admin page.")
        return False

    return True


def create_api_settings(scan: InternetNLV2Scan):
    if not valid_api_settings(scan):
        raise ValueError("Internet.nl scan settings are not configured correctly. The specific error is located in "
                         "the created internet.nl scan and visible on the admin page.")

    s = InternetNLApiSettings()
    s.username = config.INTERNET_NL_API_USERNAME
    s.password = config.INTERNET_NL_API_PASSWORD

    s.url = config.INTERNET_NL_API_URL

    # for convenience, remove trailing slashes from the url, this will be entered incorrectly.
    s.url = s.url.rstrip("/")

    s.maximum_domains = config.INTERNET_NL_MAXIMUM_URLS
    return s


@app.Task(queue="storage")
def initialize_scan(scan_type: str, domains: List[Url]):
    scan = InternetNLV2Scan()
    scan.type = scan_type
    scan.save()

    # many to many requires an object to exist.
    scan.subject_urls = domains
    scan.save()

    update_state(scan, "requested", "requested a scan to be performed on internet.nl")


@app.task(queue='storage')
def check_running_internet_nl_scans() -> Task:
    scans = InternetNLV2Scan.objects.all().exclude(state__in=['finished', 'error', 'cancelled'])
    log.debug(f"Checking the state of scan {scans}.")
    tasks = [progress_running_scan(scan) for scan in scans]

    return group(tasks)


def progress_running_scan(scan: InternetNLV2Scan) -> Task:
    """
    This monitors the state of an internet.nl scan. Depending on the state, it determines if an action is needed and
    gathers them. This will not handle errors.

    This is used in conjunction with Celery: all tasks are performed async, which scales better.

    Steps are split into two: the active verb and the past tense verb. When something is happening, the active verb
    is used, otherwise the past tense verb. Such as: "scanning endpoints" and "scanned endpoints".
        An active verb means that something is currently being performed.
        A completed / past tense verb means that the process is ready to move on.

    All active verbs have a timeout. This timeout can be different for each verb. The timeout is set to a value that
    takes into account the possibility of the system being very busy and all queues full. Therefore, something that
    usually would last 10 seconds, will have a timeout of several hours. If this timeout triggers, there is something
    very wrong: either an unexpected exception stopped the process or there are deadlocks in the queues.
        These timeouts should never be triggered: if they do, it will mean manual intervention to fix a bug etc.

    When a timeout is reached on an active verb, it will change the state to something that is not processed in this
    monitor anymore. Manual action is required, after the manual action has been performed, the person handling it
    can set the state of the failed scan to something this process understands, and we'll happily try again.
        Note that celery can also perform several attempts on exceptions etc, this might or might not happen.
        Timeouts are stored as the following: timeout on [active verb]: timeout on scanning endpoints.

    To prevent duplicate tasks from spawning, this method will adjust the task before the actual content is called.

    This does not use django fsm, as that ties everything to a model. It also over complicates the process with
    branching and such. The on-error feature is nice though.

    :return:
    """

    """
    It's not possible to safely create a scan automatically: this might be called a few times in a row, and then
    you'll end up with several new scans. Therefore, to initiate a scan, you need to call another method.
    After the scan is initiated, this will pick it up and continue.
    """
    if not scan:
        return group([])

    steps = {
        # complete state progression, using active verbs to come to the next state:
        "requested":  registering_scan_at_internet_nl,
        "registered": running_scan,
        "running scan": continue_running_scan,
        "scan results ready": storing_scan_results,
        "scan results stored": processing_scan_results,
        # "finished"

        # recovery steps in case of (network) errors
        "network_error": recover_and_retry,
        "error": recover_and_retry
    }

    with transaction.atomic():
        # always get the latest state, so we'll not have outdated information if we had to wait in a queue a long while.
        # also run this in a transaction, so it's only possible to get a state and update it to an active state once.
        scan = InternetNLV2Scan.objects.get(id=scan.id)
        next_step = steps.get(scan.state, handle_unknown_state)
        return next_step(scan)


def recover_and_retry(scan: InternetNLV2Scan):
    # todo: implement.
    # check the latest valid state from progress running scan, set the state to that state.

    valid_states = ['requested', 'registered', 'running scan', 'scan results ready', 'scan results stored']

    # get the latest valid state from the scan log:
    latest_valid = InternetNLV2StateLog.objects.all().filter(scan=scan, state__in=valid_states).order_by('-id').first()

    return group(update_state(scan, latest_valid.state, "Recovered from error state."))


def handle_unknown_state(scan):
    # probably nothing to be done... there are many intermediate states that hold all kinds of in between states.
    return group([])


def registering_scan_at_internet_nl(scan: InternetNLV2Scan):
    update_state(scan, "registering", "registering scan at internet.nl")

    # todo: get some information about this installation, so we can track requests easier.
    #  For example the target county, organization running the scan.
    scan_name = {
        'source': 'Web Security Map',
        'type': scan.type
    }

    return (
        get_relevant_urls.si(scan)
        | register.s(
            scan.type,
            json.dumps(scan_name),
            create_api_settings(scan)
        )
        | registration_administration.s(scan)
    )


def running_scan(scan: InternetNLV2Scan):
    update_state(scan, "running scan", "Running scan at internet.nl")

    return (status.si(scan.scan_id, create_api_settings(scan))
            | status_administration.s(scan))


def continue_running_scan(scan: InternetNLV2Scan):
    return (status.si(scan.scan_id, create_api_settings(scan))
            | status_administration.s(scan))


def storing_scan_results(scan: InternetNLV2Scan):
    update_state(scan, "storing scan results", "")

    return (result.si(scan.scan_id, create_api_settings(scan))
            | result_administration.s(scan))


def processing_scan_results(scan: InternetNLV2Scan):
    update_state(scan, "processing scan results", "")

    return process_scan_results.s(scan)


def update_state(scan: InternetNLV2Scan, new_state: str, new_state_message: str):

    # see if we need to update anything
    existing_log = InternetNLV2StateLog.objects.all().filter(scan=scan).order_by("-at_when").first()

    if existing_log:

        # in case there is already a scan, and no state change:
        if existing_log.state == new_state and existing_log.state_message == new_state_message:
            scan.last_state_check = datetime.now(pytz.utc)
            scan.save()

            existing_log.last_state_check = datetime.now(pytz.utc)
            existing_log.save()
            return

    scan.state = new_state
    scan.state_message = new_state_message
    scan.last_state_check = datetime.now(pytz.utc)
    scan.save()

    statelog = InternetNLV2StateLog()
    statelog.scan = scan
    statelog.at_when = datetime.now(pytz.utc)
    statelog.state = new_state
    statelog.state_message = new_state_message
    statelog.last_state_check = datetime.now(pytz.utc)
    statelog.save()


def api_has_usable_response(response, scan):

    status_code, response_content = response

    if status_code == 599:
        # using the log the previous actionable state can be retrieved as a recovery strategy.
        update_state(scan, "network_error", response_content['error_message'])
        return False

    if status_code == 500:
        update_state(scan, "server_error", "")
        return False

    if status_code == 401:
        update_state(scan, "credential_error", "")
        return False

    if status_code == 200:
        return True


########################################################################################################################
#
# Tasks
#
########################################################################################################################

@app.task(queue="storage")
def get_relevant_urls(scan: InternetNLV2Scan) -> List[str]:
    return scan.subject_urls.objects.all().values_list('url', flat=True)


@app.Task(queue="storage")
def registration_administration(response: Tuple[int, dict], scan: InternetNLV2Scan):
    """
    {

        "id": "f284049256dd4ca793edbcd4ae41759a",
        "metadata":

        {
            "tracking_information": "{'name': 'My scan 1337', 'id': '42'}",
            "scan_type": "web",
            "api_version": "2",
            "submission_date": "2020-03-26T10:24:06Z",
            "finished_date": "2020-03-26T10:24:06Z"
        }

    }

    :param response: response from internet.nl
    :param scan:
    :return:
    """

    if not api_has_usable_response(response, scan):
        return

    status_code, response_content = response

    scan = InternetNLV2Scan()
    scan.scan_id = response_content['id']
    scan.metadata = response_content['metadata']
    scan.type = response_content['metadata']['scan_type']
    scan.save()

    update_state(scan, "registered", "scan registered at internet.nl")


@app.Task(queue="storage")
def status_administration(response: Tuple[int, dict], scan: InternetNLV2Scan):
    """
    {
        "id": "f284049256dd4ca793edbcd4ae41759a",
        "status": "finished",
        "message": "Batch request is registering domains",
        "metadata":
        {
            "tracking_information": "{'name': 'My scan 1337', 'id': '42'}",
            "scan_type": "web",
            "api_version": "2",
            "submission_date": "2020-03-26T10:24:06Z",
            "finished_date": "2020-03-26T10:24:06Z"
        }
    }

    :param response:
    :param scan:
    :return:
    """
    if not api_has_usable_response(response, scan):
        return

    status_code, response_content = response

    if response_content['status'] == 'error':
        update_state(scan, "error", response_content['message'])
        return

    if response_content['status'] == 'running':
        # follow scan progression at internet.nl, update the status message with that information.
        update_state(scan, "running scan", response_content['message'])
        return

    if response_content['status'] == 'finished':
        update_state(scan, "scan results ready", response_content['message'])
        return

    # handle any other API result, that does not conform with the API spec. Update the state for debugging information.
    update_state(scan, response_content['status'], response_content['message'])
    raise ValueError("Unsupported response from the Internet.nl API received.")


@app.Task(queue="storage")
def result_administration(response: Tuple[int, dict], scan: InternetNLV2Scan):
    """
    Stores the scan metadata and domains.

    {
        "id": "f284049256dd4ca793edbcd4ae41759a",
        "metadata": {},
        "domains": {}
    }
    :param response:
    :param scan:
    :return:
    """

    if not api_has_usable_response(response, scan):
        return

    status_code, response_content = response

    scan.metadata = response_content['metadata']
    scan.retrieved_scan_report = response_content['domains']
    scan.save()

    update_state(scan, "scan results stored", "")


@app.Task(queue="storage")
def process_scan_results(scan: InternetNLV2Scan):
    scan_type_to_protocol = {
        # mail is used for web security map, it is a subset of mail servers that dedupes servers on cnames.
        'mail': 'dns_mx_no_cname',

        # dns soa are internet.nl dashboard scans that have a different requirement set for the mailserver endpoint
        'mail_dashboard': 'dns_soa',

        # web scans are only used by the internet.nl dashboard...
        'web': 'dns_a_aaaa'
    }

    domains = scan.retrieved_scan_report.keys()

    for domain in domains:

        store_domain_scan_results(
            domain=domain,
            scan_data=scan.retrieved_scan_report[domain],
            scan_type=scan.type,
            endpoint_protocol=scan_type_to_protocol[scan.type]
        )

    update_state(scan, "scan results processed", "")
    update_state(scan, "finished", "")


@app.Task(queue="storage")
def store_domain_scan_results(domain: str, scan_data: dict, scan_type: str, endpoint_protocol: str):
    """

        "internet.nl": {
            "domain": "api.internet.nl",
            "status": "success",
            "score": {
                "percentage": 80
            },
            "report":
            {
                "id": 0,
                "address": "https://api.internet.nl/web/api.internet.nl/4423123/"
            },
            "results":
            {
                "web_ipv6_ns_address":
                {
                    "test": "web_ipv6_ns_address",
                    "verdict": "good",
                    "test_result": "pass",
                    "translation": {
                        "key": "string"
                    },
                    "technical_details":
                    {
                        "data_matrix":
                        [

                            [
                                "string"
                            ]
                        ]
                    }

                }
            }
        }

    :return:
    :param domain: a domain name, such as "internet.nl"
    :param scan_data: the scan data for a specific domain
    :param scan_type: web, mail, mail_dashboard
    :param endpoint_protocol: to what endpoint of this domain the result data has to be connected.
    :return:
    """

    # Match the endpoint. We're not implicitly adding endpoints.
    endpoint = Endpoint.objects.all().filter(protocol=endpoint_protocol, url__url=domain, is_dead=False).first()

    if not endpoint:
        log.debug("No matching endpoint found, perhaps this was deleted / resolvable meanwhile. Skipping")
        return

    # link changes every time, so can't save that as message. -> _wrong_
    # The link changes every time and thus does the link to the report that will be referred in our own reports
    # and the latest link is always the one that people are interested in. Even more so: the installations of
    # internet.nl sometimes change these links, causing old links to not work anymore.
    # What CAN happen is that several scans are ran by different accounts, and that the latest result is picked
    # which was from another user. But that will take all updates from that scan, so it's up to date. These are
    # edge cases that are in here by design: we always want to get data from a certain point in time, regardless
    # who started the scan.
    store_endpoint_scan_result(
        scan_type=f'internet_nl_{scan_type}_overall_score',
        endpoint=endpoint,
        rating=scan_data['scoring']['percentage'],
        message=scan_data['report'],
        evidence=scan_data['report']
    )

    # categories (ie, derived from the test results)
    for category in scan_data['categories'].keys():
        scan_type = f'internet_nl_{scan_type}_{category}'
        store_endpoint_scan_result(
            scan_type=scan_type,
            endpoint=endpoint,
            rating=scan_data["category"][category]["verdict"],
            message='',
            evidence=scan_data['report']
        )

    # There are a number of "custom" fields that should be treated the same. These are calculations over the
    # scan results and help users deriving certain conclusions.
    # todo: does that contain the not_applicable stuff? that should be moved to the API
    store_test_results(endpoint, scan_data['results']['custom'])

    # standard tests:
    store_test_results(endpoint, scan_data['results']['tests'])

    if scan_type == "web":
        scan_data = calculate_forum_standaardisatie_views_web(scan_data)
    else:
        scan_data = calculate_forum_standaardisatie_views_mail(scan_data)

    test_results_keys = scan_data['derived_results'].keys()
    for test_result_key in test_results_keys:
        test_result = scan_data['results'][test_result_key]

        scan_type = f'internet_nl_{test_result_key}'
        store_endpoint_scan_result(
            scan_type=scan_type,
            endpoint=endpoint,
            rating=test_result['test_result'],
            message="{'translation': '', 'verdict': ''}",
            evidence=json.dumps(test_result['technical_details'])
        )


def store_test_results(endpoint, test_results):

    # this way new fields are automatically added
    test_results_keys = test_results.keys()

    for test_result_key in test_results_keys:
        test_result = test_results[test_result_key]

        scan_type = f'internet_nl_{test_result_key}'

        # technical_details can change, and these changes should always be reflected in the data. In our model
        # only rating and message are treated as unique. The technical data is often very long and will not fit
        # in either rating and message, and will cause delays in working with these fields. What we do instead is
        # create a hash and append it to the message. Technical details are an array of array of string
        dumped_technical_details = json.dumps(test_result['technical_details'])
        technical_details_hash = hashlib.md5(dumped_technical_details.encode('utf-8')).hexdigest()

        store_endpoint_scan_result(
            scan_type=scan_type,
            endpoint=endpoint,
            rating=test_result['status'],
            message=json.dumps(
                {'translation': test_result['verdict'],
                 'technical_details_hash': technical_details_hash}
            ),
            evidence=json.dumps(test_result['technical_details'])
        )

def add_calculation(scan_data, new_key: str, required_values: List[str]):
    scan_data['derived_results'][new_key] = {
        'result': true_when_all_pass(scan_data, required_values)
    }


def true_when_all_pass(scan_data, test_names) -> {}:

    if not scan_data:
        raise ValueError('No views provided. Something went wrong in the API response?')

    if not test_names:
        raise ValueError('No values provided. Would always result in True, which could be risky.')

    for test_name in test_names:
        if scan_data['results'][test_name]['test_result'] not in ['pass']:
            return False

    return True


def calculate_forum_standaardisatie_views_web(scan_data):
    # These values are published in the forum standaardisatie magazine.

    # DNSSEC
    add_calculation(scan_data=scan_data, new_key='web_legacy_dnssec',
                    required_values=['web_dnssec_exist', 'web_dnssec_valid'])

    # TLS
    add_calculation(scan_data=scan_data, new_key='web_legacy_tls_available',
                    required_values=['web_https_http_available'])

    # TLS_NCSC
    add_calculation(scan_data=scan_data, new_key='web_legacy_tls_ncsc_web',
                    required_values=['web_https_tls_version', 'web_https_tls_ciphers', 'web_https_tls_keyexchange',
                                     'web_https_tls_compress', 'web_https_tls_secreneg', 'web_https_tls_clientreneg',
                                     'web_https_cert_chain', 'web_https_cert_pubkey', 'web_https_cert_sig',
                                     'web_https_cert_domain'])

    # HTTPS
    add_calculation(scan_data=scan_data, new_key='web_legacy_https_enforced',
                    required_values=['web_https_http_redirect'])

    # HSTS
    add_calculation(scan_data=scan_data, new_key='web_legacy_hsts',
                    required_values=['web_https_http_hsts'])

    # Not in forum standaardisatie magazine, but used internally
    add_calculation(scan_data=scan_data, new_key='web_legacy_ipv6_nameserver',
                    required_values=['web_ipv6_ns_address', 'web_ipv6_ns_reach'])

    # Not in forum standaardisatie magazine, but used internally
    add_calculation(scan_data=scan_data, new_key='web_legacy_ipv6_webserver',
                    required_values=['web_ipv6_ws_address', 'web_ipv6_ws_reach', 'web_ipv6_ws_similar'])

    # Not in forum standaardisatie magazine, but used internally
    add_calculation(scan_data=scan_data, new_key='web_legacy_dane',
                    required_values=['web_https_dane_exist', 'web_https_dane_valid'])

    return scan_data


def calculate_forum_standaardisatie_views_mail(scan_data):
    # These values are published in the forum standaardisatie magazine.

    # DMARC
    add_calculation(scan_data=scan_data, new_key='mail_legacy_dmarc', required_values=['mail_auth_dmarc_exist'])

    # DKIM
    add_calculation(scan_data=scan_data, new_key='mail_legacy_dkim', required_values=['mail_auth_dkim_exist'])

    # SPF
    add_calculation(scan_data=scan_data, new_key='mail_legacy_spf', required_values=['mail_auth_spf_exist'])

    # DMARC Policy
    add_calculation(scan_data=scan_data, new_key='mail_legacy_dmarc_policy',
                    required_values=['mail_auth_dmarc_policy_only'])

    # SPF Policy
    add_calculation(scan_data=scan_data, new_key='mail_legacy_spf_policy', required_values=['mail_auth_spf_policy'])

    # START TLS
    add_calculation(scan_data=scan_data, new_key='mail_legacy_start_tls',
                    required_values=['mail_starttls_tls_available'])

    # START TLS NCSC
    # mail_starttls_cert_domain is mandatory ONLY when mail_starttls_dane_ta is True.
    # todo: the mail_starttls_dane_ta value is not returned anymore. Is there a verdict that matches this scenario?
    # todo: this will problably be a custom field?
    start_tls_ncsc_fields = \
        ['mail_starttls_tls_available', 'mail_starttls_tls_version', 'mail_starttls_tls_ciphers',
         'mail_starttls_tls_keyexchange', 'mail_starttls_tls_compress', 'mail_starttls_tls_secreneg',
         'mail_starttls_cert_pubkey', 'mail_starttls_cert_sig']

    if scan_data['results']['mail_starttls_dane_ta']['verdict'] == "[TODO]":
        start_tls_ncsc_fields.append('mail_starttls_cert_domain')

    add_calculation(scan_data=scan_data, new_key='mail_legacy_start_tls_ncsc', required_values=start_tls_ncsc_fields)

    # Not in forum standardisatie magazine, but used internally
    add_calculation(scan_data=scan_data, new_key='mail_legacy_dnssec_email_domain',
                    required_values=['mail_dnssec_mailto_exist', 'mail_dnssec_mailto_valid'])

    # DNSSEC MX
    add_calculation(scan_data=scan_data, new_key='mail_legacy_dnssec_mx',
                    required_values=['mail_dnssec_mx_exist', 'mail_dnssec_mx_valid'])

    # DANE
    add_calculation(scan_data=scan_data, new_key='mail_legacy_dane',
                    required_values=['mail_starttls_dane_exist', 'mail_starttls_dane_valid'])

    # Not in forum standardisatie magazine, but used internally
    add_calculation(scan_data=scan_data, new_key='mail_legacy_ipv6_nameserver',
                    required_values=['mail_ipv6_ns_address', 'mail_ipv6_ns_reach'])

    # Not in forum standardisatie magazine, but used internally
    add_calculation(scan_data=scan_data, new_key='mail_legacy_ipv6_mailserver',
                    required_values=['mail_ipv6_mx_address', 'mail_ipv6_mx_reach'])

    return scan_data
