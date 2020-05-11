"""
Web Security Map implementation of internet.nl scans.
"""

import hashlib
import ipaddress
import json
import logging
from copy import copy
from datetime import datetime, timedelta
from typing import List, Tuple

import pytz
import tldextract
from celery import Task, group
from constance import config
from django.db import transaction

from websecmap.celery import app
from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint, InternetNLV2Scan, InternetNLV2StateLog
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.internet_nl_v2 import (InternetNLApiSettings, register, result,
                                                       status)

log = logging.getLogger(__name__)


def valid_api_settings(scan: InternetNLV2Scan):
    if not config.INTERNET_NL_API_USERNAME:
        update_state(scan, "configuration_error",
                     "Username for internet.nl scan not configured. "
                     "This setting can be configured in the settings on the admin page.")
        return False

    if not config.INTERNET_NL_API_PASSWORD:
        update_state(scan, "configuration_error",
                     "Password for internet.nl scan not configured. "
                     "This setting can be configured in the settings on the admin page.")
        return False

    if not config.INTERNET_NL_API_URL:
        update_state(scan, "configuration_error",
                     "No url supplied for internet.nl scans. "
                     "This setting can be configured in the settings on the admin page.")
        return False

    # validate the url itself:
    extract = tldextract.extract(config.INTERNET_NL_API_URL)
    if not extract.suffix:
        # can can still be an IP address, which should work too
        try:
            ipaddress.ip_address(extract.domain)
        except ValueError:
            update_state(scan, "configuration_error",
                         "The internet.nl api url is not a valid url or IP format. Always start with "
                         "https:// and then the address. "
                         "This setting can be configured in the settings on the admin page.")
            return False

    if not config.INTERNET_NL_MAXIMUM_URLS:
        update_state(scan,
                     "configuration_error",
                     "No maximum supplied for the amount of urls in an internet.nl scans. "
                     "This setting can be configured in the settings on the admin page.")
        return False

    return True


def create_api_settings(scan: InternetNLV2Scan):
    s = InternetNLApiSettings()
    s.username = config.INTERNET_NL_API_USERNAME
    s.password = config.INTERNET_NL_API_PASSWORD

    s.url = config.INTERNET_NL_API_URL
    # for convenience, remove trailing slashes from the url, this will be entered incorrectly.
    s.url = s.url.rstrip("/")

    s.maximum_domains = config.INTERNET_NL_MAXIMUM_URLS

    return s


@app.task(queue="storage")
def initialize_scan(scan_type: str, domains: List[Url]):
    scan = InternetNLV2Scan()
    scan.type = scan_type
    scan.save()

    max_urls = config.INTERNET_NL_MAXIMUM_URLS
    if len(domains) > max_urls:
        update_state(scan, "configuration_error",
                     f"Too many domains: {len(domains)} is more than {max_urls}. Not registering. Try "
                     f"again with fewer domains or change the maximum accordingly.")
        return scan

    # many to many requires an object to exist.
    scan.subject_urls.set(domains)

    update_state(scan, "requested", "requested a scan to be performed on internet.nl api")

    return scan


@app.task(queue='storage')
def check_running_internet_nl_scans() -> Task:
    scans = InternetNLV2Scan.objects.all().exclude(state__in=['finished', 'error', 'cancelled'])
    log.debug(f"Checking the state of scan {scans}.")
    tasks = [progress_running_scan(scan) for scan in scans]

    return group(tasks)


@app.task(queue='storage')
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
        "configuration_error": recover_and_retry,
        "timeout": recover_and_retry
    }

    with transaction.atomic():
        # always get the latest state, so we'll not have outdated information if we had to wait in a queue a long while.
        # also run this in a transaction, so it's only possible to get a state and update it to an active state once.
        # because this is a transaction, crashes such as value errors are not written to the database.
        scan = InternetNLV2Scan.objects.get(id=scan.id)
        next_step = steps.get(scan.state, handle_unknown_state)
        log.debug(f"Internet.nl scan #{scan.id} is being progressed from {scan.state}.")
        return next_step(scan)


@app.task(queue="storage")
def recover_and_retry(scan: InternetNLV2Scan):
    # check the latest valid state from progress running scan, set the state to that state.

    valid_states = ['requested', 'registered', 'running scan', 'scan results ready', 'scan results stored']
    error_states = ["network_error", "configuration_error", "timeout"]

    if scan.state in valid_states:
        # no recovery needed
        return group([])

    # get the latest valid state from the scan log:
    latest_valid = InternetNLV2StateLog.objects.all().filter(scan=scan, state__in=valid_states).order_by('-id').first()

    log.debug(f"Internet.nl scan #{scan.id} is rolled back to retry from '{scan.state}' to '{latest_valid.state}'.")

    if scan.state in error_states:
        update_state(scan, latest_valid.state, f"Rolled back from error state '{scan.state}', retrying.")
    else:
        update_state(scan, latest_valid.state, f"Rolled back from miscellaneous state '{scan.state}', retrying.")

    return group([])


def handle_unknown_state(scan):
    # probably nothing to be done... there are many intermediate states that hold all kinds of in between states.

    # we can however deal with timeouts. If an unknown state is over a certain time, the task should be tried again.

    timeouts = {
        'registering': 3600 * 24,  # 24 hours
        'storing scan results': 3600 * 24,
        'processing scan results': 3600 * 24
    }

    # not the state check, but the moment the state was created...
    if scan.state in timeouts:
        if scan.last_state_change + timedelta(seconds=timeouts[scan.state]) < datetime.now(pytz.utc):
            return group(update_state(scan, "timeout", f"The state '{scan.state}' timed out, attempting to retry."))

    return group([])


def registering_scan_at_internet_nl(scan: InternetNLV2Scan):
    update_state(scan, "registering", "registering scan at internet.nl")

    # todo: get some information about this installation, so we can track requests easier.
    #  For example the target county, organization running the scan.
    scan_name = {
        'source': 'Web Security Map',
        'type': scan.type
    }

    if not valid_api_settings(scan):
        return group([])

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

    if not valid_api_settings(scan):
        return group([])

    return (status.si(scan.scan_id, create_api_settings(scan))
            | status_administration.s(scan))


def continue_running_scan(scan: InternetNLV2Scan):

    if not valid_api_settings(scan):
        return group([])

    return (status.si(scan.scan_id, create_api_settings(scan))
            | status_administration.s(scan))


def storing_scan_results(scan: InternetNLV2Scan):
    update_state(scan, "storing scan results", "")

    if not valid_api_settings(scan):
        return group([])

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

    old_state = copy(scan.state)
    scan.state = new_state
    scan.state_message = new_state_message
    scan.last_state_check = datetime.now(pytz.utc)
    scan.last_state_change = datetime.now(pytz.utc)
    scan.save()

    statelog = InternetNLV2StateLog()
    statelog.scan = scan
    statelog.at_when = datetime.now(pytz.utc)
    statelog.state = new_state
    statelog.state_message = new_state_message
    statelog.last_state_check = datetime.now(pytz.utc)
    statelog.save()

    log.debug(f"Internet.nl scan #{scan.id} state changed from '{old_state}' to '{new_state}'.")


def api_has_usable_response(response, scan):

    status_code, response_content = response

    if status_code == 599:
        # using the log the previous actionable state can be retrieved as a recovery strategy.
        update_state(scan, "network_error", response_content['error']['label'])
        return False

    if status_code == 500:
        update_state(scan, "server_error", "")
        return False

    if status_code == 401:
        update_state(scan, "credential_error", "")
        return False

    if status_code == 400:
        update_state(scan, "error", json.dumps(response_content))
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
    return list(scan.subject_urls.all().values_list('url', flat=True))


@app.task(queue="storage")
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

    # todo: duplicated "request" in "request".
    scan.scan_id = response_content['request']['request_id']
    scan.metadata = response_content['request']
    scan.type = response_content['request']['request_type']
    scan.save()

    update_state(scan, "registered", "scan registered at internet.nl")


@app.task(queue="storage")
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

    if response_content['request']['status'] == 'registering':
        # follow scan progression at internet.nl, update the status message with that information.
        update_state(scan, "running scan", response_content['request']['status'])
        return

    if response_content['request']['status'] == 'running':
        # follow scan progression at internet.nl, update the status message with that information.
        update_state(scan, "running scan", response_content['request']['status'])
        return

    if response_content['request']['status'] == 'generating':
        # follow scan progression at internet.nl, update the status message with that information.
        update_state(scan, "running scan", response_content['request']['status'])
        return

    if response_content['request']['status'] == 'done':
        update_state(scan, "scan results ready", response_content['request']['status'])
        return

    if response_content['request']['status'] == 'error':
        update_state(scan, "error", response_content['request']['status'])
        return

    # handle any other API result, that does not conform with the API spec. Update the state for debugging information.
    # the progress will most likely hang. Such as with cancelled.
    update_state(scan, response_content['request']['status'], response_content['request']['status'])


@app.task(queue="storage")
def result_administration(response: Tuple[int, dict], scan: InternetNLV2Scan):
    """
    Stores the scan metadata and domains.

    {
        api_version...
        "request": {},
        "domains": {}
    }
    :param response:
    :param scan:
    :return:
    """

    if not api_has_usable_response(response, scan):
        return

    status_code, response_content = response

    scan.metadata = response_content['request']
    scan.retrieved_scan_report = response_content['domains']
    scan.save()

    update_state(scan, "scan results stored", "")


@app.task(queue="storage")
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


@app.task(queue="storage")
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
        message=scan_data['report']['url'],
        evidence=scan_data['report']['url']
    )

    # categories (ie, derived from the test results)
    # no technical details here:
    for category in scan_data['results']['categories'].keys():

        # to keep APIv2 in line with APIv2, so we don't have to rename fields:
        if scan_type == "web":
            scan_type_field = f'internet_nl_{category}'
        else:
            scan_type_field = f'internet_nl_{scan_type}_{category}',

        store_endpoint_scan_result(
            scan_type=scan_type_field,
            endpoint=endpoint,
            rating=scan_data['results']['categories'][category]["status"],
            message=json.dumps(
                {'translation': scan_data['results']['categories'][category]["verdict"],
                 'technical_details_hash': ''}
            ),
            evidence=scan_data['report']['url']
        )

    # standard tests:
    store_test_results(endpoint, scan_data['results']['tests'])

    # prepare for calculated results
    scan_data['results']['calculated_results'] = {}
    if scan_type == "web":
        scan_data = calculate_forum_standaardisatie_views_web(scan_data, scan_data['results']['custom'])
    elif scan_type == 'mail_dashboard':
        scan_data = calculate_forum_standaardisatie_views_mail(scan_data, scan_data['results']['custom'])

    store_test_results(endpoint, scan_data['results']['calculated_results'])


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
        # log.debug(f"{scan_type}  = {test_result}")
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
    could_be_true = true_when_all_pass(scan_data, required_values)

    scan_data['results']['calculated_results'][new_key] = {
        'status': 'passed' if could_be_true else 'failed',
        'verdict': 'passed' if could_be_true else 'failed',
        'technical_details': [],
    }


def add_instant_calculation(scan_data, key, value):

    scan_data['results']['calculated_results'][key] = {
        'status': value,
        'verdict': value,
        'technical_details': [],
    }


def true_when_all_pass(scan_data, test_names) -> {}:

    if not scan_data:
        raise ValueError('No views provided. Something went wrong in the API response?')

    if not test_names:
        raise ValueError('No values provided. Would always result in True, which could be risky.')

    for test_name in test_names:
        if scan_data['results']['tests'][test_name]['status'] not in ['passed']:
            return False

    return True


def calculate_forum_standaardisatie_views_web(scan_data, custom_api_field_results):
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
                                     'web_https_tls_compression', 'web_https_tls_secreneg', 'web_https_tls_clientreneg',
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


def calculate_forum_standaardisatie_views_mail(scan_data, custom_api_field_results):
    # These values are published in the forum standaardisatie magazine.

    # DMARC
    add_calculation(scan_data=scan_data, new_key='mail_legacy_dmarc', required_values=['mail_auth_dmarc_exist'])

    # DKIM
    if custom_api_field_results['mail_non_sending_domain']:
        add_instant_calculation(scan_data, "mail_legacy_dkim", "not_applicable")
    else:
        add_calculation(scan_data=scan_data, new_key='mail_legacy_dkim', required_values=['mail_auth_dkim_exist'])

    # SPF
    add_calculation(scan_data=scan_data, new_key='mail_legacy_spf', required_values=['mail_auth_spf_exist'])

    # DMARC Policy
    #
    add_instant_calculation(scan_data, "mail_legacy_dmarc_policy",
                            'passed' if custom_api_field_results['mail_auth_dmarc_policy_only'] else 'failed')

    # SPF Policy
    add_calculation(scan_data=scan_data, new_key='mail_legacy_spf_policy', required_values=['mail_auth_spf_policy'])

    # START TLS
    if not custom_api_field_results['mail_server_configured']:
        add_instant_calculation(scan_data, 'mail_legacy_start_tls', "not_applicable")
    elif not custom_api_field_results['mail_servers_testable']:
        add_instant_calculation(scan_data, 'mail_legacy_start_tls', "not_testable")
    else:
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

    if custom_api_field_results['mail_starttls_dane_ta']:
        start_tls_ncsc_fields.append('mail_starttls_cert_domain')

    if not custom_api_field_results['mail_server_configured']:
        add_instant_calculation(scan_data, 'mail_legacy_start_tls_ncsc', "not_applicable")
    elif not custom_api_field_results['mail_servers_testable']:
        add_instant_calculation(scan_data, 'mail_legacy_start_tls_ncsc', "not_testable")
    else:
        add_calculation(scan_data=scan_data, new_key='mail_legacy_start_tls_ncsc',
                        required_values=start_tls_ncsc_fields)

    # Not in forum standardisatie magazine, but used internally
    add_calculation(scan_data=scan_data, new_key='mail_legacy_dnssec_email_domain',
                    required_values=['mail_dnssec_mailto_exist', 'mail_dnssec_mailto_valid'])

    # DNSSEC MX
    if not custom_api_field_results['mail_server_configured']:
        add_instant_calculation(scan_data, 'mail_dnssec_mx_exist', "not_applicable")
    else:
        add_calculation(scan_data=scan_data, new_key='mail_legacy_dnssec_mx',
                        required_values=['mail_dnssec_mx_exist', 'mail_dnssec_mx_valid'])

    # DANE
    if not custom_api_field_results['mail_server_configured']:
        add_instant_calculation(scan_data, 'mail_legacy_dane', "not_applicable")
    elif not custom_api_field_results['mail_servers_testable']:
        add_instant_calculation(scan_data, 'mail_legacy_dane', "not_testable")
    else:
        add_calculation(scan_data=scan_data, new_key='mail_legacy_dane',
                        required_values=['mail_starttls_dane_exist', 'mail_starttls_dane_valid'])

    # Not in forum standardisatie magazine, but used internally
    if not custom_api_field_results['mail_server_configured']:
        add_instant_calculation(scan_data, 'mail_ipv6_ns_address', "not_applicable")
    else:
        add_calculation(scan_data=scan_data, new_key='mail_legacy_ipv6_nameserver',
                        required_values=['mail_ipv6_ns_address', 'mail_ipv6_ns_reach'])

    # Not in forum standardisatie magazine, but used internally
    if not custom_api_field_results['mail_server_configured']:
        add_instant_calculation(scan_data, 'mail_ipv6_mx_address', "not_applicable")
    else:
        add_calculation(scan_data=scan_data, new_key='mail_legacy_ipv6_mailserver',
                        required_values=['mail_ipv6_mx_address', 'mail_ipv6_mx_reach'])

    return scan_data
