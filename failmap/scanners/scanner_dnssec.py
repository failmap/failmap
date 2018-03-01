"""Scans DNSSEC using the dotSE DNSCHECK tool.

Installing this tool may be a bit difficult if you've never tried. So just use docker.
https://github.com/dotse/dnscheck/tree/master/engine

On a mac you might first want to:
brew install perl

CPAN install TAP::Harness::Env
CPAN install File::ShareDir::Install

and then follow the installation instructions.

todo: You'll end up with DNSCheck missing in $... forget it, use docker!


"""

import logging
import random
import subprocess
from typing import List

from celery import Task, group
from django.conf import settings

from failmap.celery import ParentFailed, app
from failmap.organizations.models import Organization, Url
from failmap.scanners.endpoint_scan_manager import EndpointScanManager

from .models import Endpoint

log = logging.getLogger(__name__)

# how often a task should be retried when encountering an expectable exception
MAX_RETRIES = 3
RETRY_DELAY = 1
# after which time a pending task should no longer be accepted by a worker
EXPIRES = 5


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    """Compose taskset to scan specified endpoints.

    """
    # apply filter to organizations (or if no filter, all organizations)
    organizations = Organization.objects.filter(**organizations_filter)
    # apply filter to urls in organizations (or if no filter, all urls)
    urls = Url.objects.filter(organization__in=organizations, **urls_filter)

    # select endpoints to scan based on filters
    endpoints = Endpoint.objects.filter(
        # apply filter to endpoints (or if no filter, all endpoints)
        url__in=urls, **endpoints_filter,
        # also apply manditory filters to only select valid endpoints for this action
        is_dead=False, protocol__in=['http', 'https'])

    if not endpoints:
        raise Exception('Applied filters resulted in no tasks!')

    log.info('Creating scan task for %s endpoints for %s urls for %s organizations.',
             len(endpoints), len(urls), len(organizations))

    # todo: this is a poor mans solution for queue randomization, will be implemented in the queue manager
    # make sure we're dealing with a list for the coming random function
    endpoints = list(endpoints)
    # randomize the endpoints so hosts are contacted in random order (less pressure)
    random.shuffle(endpoints)

    # create tasks for scanning all selected endpoints as a single managable group
    # Sending entire objects is possible. How signatures (.s and .si) work is documented:
    # http://docs.celeryproject.org/en/latest/reference/celery.html#celery.signature
    task = group(
        scan_dnssec.s(endpoint.uri_url()) | store_dnssec.s(endpoint) for endpoint in endpoints
    )

    return task


@app.task(queue='storage')
def store_dnssec(result: List[str], endpoint: Endpoint):
    """

    :param result: param endpoint:
    :param endpoint:

    """
    # if scan task failed, ignore the result (exception) and report failed status
    if isinstance(result, Exception):
        return ParentFailed('skipping result parsing because scan failed.', cause=result)

    # relevant helps to store the minimum amount of information.
    level, relevant = analyze_result(result)

    # Messages are translated for display. Add the exact messages in: /failmap/map/static/js/script.js
    # Run "failmap translate" to have the messages added to:
    # /failmap/map/locale/*/djangojs.po
    # /failmap/map/locale/*/django.po
    # translate them and then run "failmap translate" again.
    messages = {
        'ERROR': 'DNSSEC is incorrectly or not configured. Use below information to debug: %s',
        'WARNING': 'DNSSEC is incorrectly configured. Use below information to debug: %s',
        'INFO_NOTICE': 'DNSSEC seems to be implemented sufficiently. %s'
    }

    log.debug('Storing result: %s, for endpoint: %s.', result, endpoint)
    # You can save any (string) value and any (string) message.
    # The EndpointScanManager deduplicates the data for you automatically.
    if result:
        EndpointScanManager.add_scan('DNSSEC', endpoint, level, messages[level] % relevant)
    else:
        EndpointScanManager.add_scan('DNSSEC', endpoint, level, messages[level] % "")

    # return something informative
    return {'status': 'success', 'result': level}


@app.task(queue='scanners',
          bind=True,
          default_retry_delay=RETRY_DELAY,
          retry_kwargs={'max_retries': MAX_RETRIES},
          expires=EXPIRES)
def scan_dnssec(self, uri_url: str):
    """
    Uses the dnssec scanner of dotse, which works pretty well.

    :param uri_url:

    Possible problems as seen on: https://github.com/stjernstedt/Interlan/blob/master/script/functions
    Timeout of 240 seconds. Nothing more (oh wow).

    """
    try:
        log.info('Start scanning %s', uri_url)

        command = "%s %s" % (settings.TOOLS['dnscheck']['executable'], uri_url)
        output = subprocess.check_output(command).decode("UTF-8")
        content = output.splitlines()

        log.info('Done scanning: %s, result: %s', uri_url, content)
        return content

    # errors:
    # subprocess.CalledProcessError non zero exit status
    # OSError: Incorrect permission, file doesn't exist, etc
    except (subprocess.CalledProcessError, OSError) as e:
        # If an expected error is encountered put this task back on the queue to be retried.
        # This will keep the chained logic in place (saving result after successful scan).
        # Retry delay and total number of attempts is configured in the task decorator.
        try:
            # Since this action raises an exception itself, any code after this won't be executed.
            raise self.retry(exc=e)
        except BaseException:
            # If this task still fails after maximum retries the last
            # error will be passed as result to the next task.
            log.exception('Retried %s times and it still failed', MAX_RETRIES)
            return e


def analyze_result(result: List[str]):
    """
    All possible outcomes:
    https://github.com/dotse/dnscheck/blob/5b0fce771259d9dfc03c6c69abba44f2be142c30/engine/t/config/policy.yaml

    dnssec.pl runs with the following settings
    my $check = new DNSCheck({ interactive => 1, extras => { debug => 0 }, localefile => 'locale/en.yaml' });

    this results in output like this:
    3.347: INFO DNSSEC signature RRSIG(faalkaart.nl/IN/SOA/40979) matches records.
    3.347: INFO DNSSEC signature valid: RRSIG(faalkaart.nl/IN/SOA/40979)
    3.347: INFO Enough valid signatures over SOA RRset found for faalkaart.nl.

    optional todo: for debugging also have the url echoed in the output.

    :return:
    """

    strings = {
        "ERROR": [],
        "WARNING": [],
        "INFO": []
    }

    for line in result:
        # remove the cringy timestamp
        line = line.strip()
        line = line[line.find(" "):len(line)].strip()
        if line.startswith("%s" % "INFO"):
            strings["INFO"].append(line)
        if line.startswith("%s" % "NOTICE"):
            strings["INFO"].append(line)
        if line.startswith("%s" % "WARNING"):
            strings["WARNING"].append(line)
        if line.startswith("%s" % "ERROR"):
            strings["ERROR"].append(line)

        # a beautiful feature of DNSCHECK is that if there is no DNSSEC, an INFO message is given.
        # We'll upgrade the severity here:
        """
        35.268: INFO Begin testing DNSSEC for gratiz.nl.
        35.301: INFO Did not find DS record for gratiz.nl at parent.
        35.374: INFO Servers for gratiz.nl have consistent extra processing status.
        35.402: INFO Authenticated denial records not found for gratiz.nl.
        35.420: INFO Did not find DNSKEY record for gratiz.nl at child.
        35.422: INFO No DNSKEY(s) found at child, other tests skipped.
        35.422: INFO Done testing DNSSEC for gratiz.nl.
        """

        # translations for the english language files
        if line.startswith("%s" % "INFO Did not find DS record"):
            strings["ERROR"].append(line)

        if line.startswith("%s" % "INFO Authenticated denial records not found"):
            strings["ERROR"].append(line)

        if line.startswith("%s" % "INFO Did not find DNSKEY"):
            strings["ERROR"].append(line)

        if line.startswith("%s" % "INFO No DNSKEY(s) found at child"):
            strings["ERROR"].append(line)

        # in case the language files are not installed:
        if line.startswith("%s" % "INFO [DNSSEC:NO_DS_FOUND]"):
            strings["ERROR"].append(line)

        if line.startswith("%s" % "INFO [DNSSEC:NSEC_NOT_FOUND]"):
            strings["ERROR"].append(line)

        if line.startswith("%s" % "INFO [DNSSEC:DNSKEY_NOT_FOUND]"):
            strings["ERROR"].append(line)

        if line.startswith("%s" % "INFO [DNSSEC:SKIPPED_NO_KEYS]"):
            strings["ERROR"].append(line)

    highest_level = "ERROR" if strings["ERROR"] \
        else "WARNING" if strings["WARNING"] \
        else "INFO" if strings["INFO"] \
        else "NONE"

    if highest_level == "NONE":
        raise ValueError("Did not correctly parse DNSSCAN result string. %s " % result)

    relevant_strings = strings[highest_level]

    return highest_level, relevant_strings


def test_analyze_result():

    # standard info
    result = """0.000: INFO Begin testing DNSSEC for faalkaart.nl.
        2.543: INFO Found DS record for faalkaart.nl at parent.
        3.175: INFO Nameserver 37.97.255.53 does DNSSEC extra processing.
        3.212: INFO Nameserver 80.69.67.67 does DNSSEC extra processing.
        3.245: INFO Nameserver 80.69.69.69 does DNSSEC extra processing.
        3.245: INFO Servers for faalkaart.nl have consistent extra processing status.
        3.282: INFO Authenticated denial records found for faalkaart.nl, of type NSEC3.
        3.296: INFO NSEC3PARAM record found for faalkaart.nl.
        3.296: INFO NSEC3 for faalkaart.nl is set to use 100 iterations, which is less than 100 and thus OK.
        3.296: INFO Found DNSKEY record for faalkaart.nl at child.
        3.296: INFO Consistent security for faalkaart.nl.
        3.297: INFO Checking DNSSEC at child (faalkaart.nl)."""

    result = result.splitlines()
    level, relevant = analyze_result(result)

    assert level == "INFO"

    # standard error
    result = """0.000: INFO Begin testing DNSSEC for faalkaart.nl.
        2.543: INFO Found DS record for faalkaart.nl at parent.
        3.175: ERROR Nameserver 37.97.255.53 does DNSSEC extra processing.
        3.348: INFO Algorithm number 7 is OK.
        3.348: INFO Parent DS(faalkaart.nl/7/2/52353) refers to valid key at child: DNSKEY(faalkaart.nl/7/52353)
        3.349: INFO Parent DS(faalkaart.nl) refers to secure entry point (SEP) at child: DS(faalkaart.nl/7/2/52353)
        3.349: INFO DNSSEC parent checks for faalkaart.nl complete.
        3.349: INFO Done testing DNSSEC for faalkaart.nl."""

    result = result.splitlines()
    level, relevant = analyze_result(result)

    assert level == "ERROR"

    # subtle missing DNSSEC
    result = """0.000: INFO Begin testing DNSSEC for faalkaart.nl.
        2.543: INFO Found DS record for faalkaart.nl at parent.
        3.175: ERROR Nameserver 37.97.255.53 does DNSSEC extra processing.
        3.348: INFO Algorithm number 7 is OK.
        3.348: INFO Parent DS(faalkaart.nl/7/2/52353) refers to valid key at child: DNSKEY(faalkaart.nl/7/52353)
        3.349: INFO Parent DS(faalkaart.nl) refers to secure entry point (SEP) at child: DS(faalkaart.nl/7/2/52353)
        3.349: INFO Did not find DS record something something darkside.
        3.349: INFO Done testing DNSSEC for faalkaart.nl."""

    result = result.splitlines()
    level, relevant = analyze_result(result)

    assert level == "ERROR"

    # missing translation files
    result = """
    0.000: INFO [DNSSEC:BEGIN] nu.nl
    1.969: INFO [DNSSEC:NO_DS_FOUND] nu.nl
    2.995: INFO [DNSSEC:CONSISTENT_EXTRA_PROCESSING] nu.nl
    3.058: INFO [DNSSEC:NSEC_NOT_FOUND] nu.nl
    3.091: INFO [DNSSEC:DNSKEY_NOT_FOUND] nu.nl
    3.091: INFO [DNSSEC:SKIPPED_NO_KEYS] nu.nl
    3.091: INFO [DNSSEC:END] nu.nl
    """

    result = result.splitlines()
    level, relevant = analyze_result(result)

    assert level == "ERROR"
