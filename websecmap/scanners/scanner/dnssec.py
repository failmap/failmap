"""Scans DNSSEC using the dotSE DNSCHECK tool.

This is also a reference implementation of a standardized scanner. This scanner works on Url level, not on endpoint
level.

It's a nightmare to get the tool running on your system so use the one in docker:
docker-build
docker-failmap-with-db scan dnssec

If you must run the DNSSEC scanner yourself, we wish you good luck. To get you started:
brew install perl

CPAN install TAP::Harness::Env
CPAN install File::ShareDir::Install

and then follow the installation instructions here:
https://github.com/dotse/dnscheck/tree/master/engine

We strongly recomend using the docker approach.
"""

import logging
import subprocess
import random
from typing import List

from celery import Task, group
from django.conf import settings
from django.db.models import Q

from websecmap.celery import ParentFailed, app
from websecmap.organizations.models import Organization, Url
from websecmap.scanners.models import Endpoint
from websecmap.scanners.scanmanager import store_url_scan_result
from websecmap.scanners.scanner.__init__ import allowed_to_scan, q_configurations_to_scan

log = logging.getLogger(__name__)

# how often a task should be retried when encountering an expectable exception
MAX_RETRIES = 3
RETRY_DELAY = 10

# after which time (seconds) a pending task should no longer be accepted by a worker
# can also be a datetime.
EXPIRES = 3600  # one hour is more then enough


def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
    **kwargs
) -> Task:
    """ Compose taskset to scan toplevel domains.

    DNSSEC is implemented on a (top level) url. It's useless to scan per-endpoint.
    This is the first scanner that uses the UrlGenericScan table, which looks nearly the same as the
    endpoint variant.
    """

    if not allowed_to_scan("dnssec"):
        return group()

    # DNSSEC only works on top level urls
    urls_filter = dict(urls_filter, **{"computed_subdomain": ""})

    # gather urls from organizations
    if organizations_filter:
        organizations = Organization.objects.filter(**organizations_filter).only('id')
        urls = Url.objects.filter(q_configurations_to_scan(),
                                  Q(computed_subdomain__isnull=True) | Q(computed_subdomain=""),
                                  organization__in=organizations,
                                  **urls_filter).only('id', 'url')
    elif endpoints_filter:
        # and now retrieve urls from endpoints
        endpoints = Endpoint.objects.filter(**endpoints_filter).only('id')
        urls = Url.objects.filter(q_configurations_to_scan(),
                                  Q(computed_subdomain__isnull=True) | Q(computed_subdomain=""),
                                  endpoint__in=endpoints,
                                  **urls_filter).only('id', 'url')
    else:
        # now urls directly
        urls = Url.objects.filter(q_configurations_to_scan(),
                                  Q(computed_subdomain__isnull=True) | Q(computed_subdomain=""),
                                  **urls_filter).only('id', 'url')

    # Optimize: only required values, unique and randomized
    urls = list(set(urls))
    random.shuffle(urls)

    log.info(f'Creating DNSSEC scan task for {len(urls)} urls.')

    # The number of top level urls is negligible, so randomization is not needed.

    # create tasks for scanning all selected endpoints as a single managable group
    # Sending entire objects is possible. How signatures (.s and .si) work is documented:
    # http://docs.celeryproject.org/en/latest/reference/celery.html#celery.signature
    task = group(
        scan_dnssec.si(url.url) | store_dnssec.s(url) for url in urls
    )

    return task


@app.task(queue='storage')
def store_dnssec(result: List[str], url: Url):
    """

    :param result:
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
        'ERROR': 'DNSSEC is incorrectly or not configured (errors found).',
        'WARNING': 'DNSSEC is incorrectly configured (warnings found).',
        'INFO': 'DNSSEC seems to be implemented sufficiently.'
    }

    log.debug('Storing result: %s, for url: %s.', result, url)
    # You can save any (string) value and any (string) message.
    # The EndpointScanManager deduplicates the data for you automatically.
    if result:
        store_url_scan_result('DNSSEC', url, level, messages[level], evidence=",\n".join(result))

    # return something informative
    return {'status': 'success', 'result': level}


# amsterdam.nl hangs on october 12 2018
# in some cases this hangs, therefore have a time limit on the task.
# "The worker processing the task will be killed and replaced with a new one when this is exceeded."
@app.task(queue='internet',
          bind=True,
          default_retry_delay=RETRY_DELAY,
          retry_kwargs={'max_retries': MAX_RETRIES},
          expires=EXPIRES,
          task_time_limit=120)
def scan_dnssec(self, url: str):
    """
    Uses the dnssec scanner of dotse, which works pretty well.

    :param url:

    Possible problems as seen on: https://github.com/stjernstedt/Interlan/blob/master/script/functions
    Timeout of 240 seconds. Nothing more (oh wow).

    """
    try:
        log.info('Start scanning %s', url)

        output = subprocess.check_output([settings.TOOLS['dnscheck']['executable'], url]).decode("UTF-8")
        content = output.splitlines()

        log.info('Done scanning: %s, result: %s', url, content)
        return content

    # subprocess.CalledProcessError: non zero exit status
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

    errors = []
    warnings = []
    infos = []

    for line in result:
        # remove the cringy timestamp
        line = line.strip()
        line = line[line.find(" "):len(line)].strip()

        # log.debug(line)

        if line.startswith("INFO"):
            infos.append(line)
        if line.startswith("NOTICE"):
            infos.append(line)
        if line.startswith("WARNING"):
            # The MISSING_DS is never a problem it seems.
            """
                This warning means that there INDEED is an OK DNSSEC implementation as long as you check the parent.

                NL:
                descr: "De child gebruikt zo te zien DNSSEC, maar de parent heeft geen veilige delegation op basis
                van DNSSEC.  Hierdoor is de 'chain of trust' tussen de parent en de child verbroken en 'validating
                resolvers', die op DNSSEC-juistheid controleren, zullen niet in staat zijn om de antwoorden van de
                child te valideren."
                format: 'De Chain of trust voor %s is niet in orde - Er is een DNSKEY aangetroffen bij de child,
                maar DS record bij de parent.'

                EN:
                descr: 'The child seems to use DNSSEC, but the parent has no secure delegation.  The chain of trust
                between the parent and the child is broken and validating resolvers will not be able to validate
                answers from the child.'
                format: 'Broken chain of trust for %s - DNSKEY found at child, but no DS was found at parent.'

                Search for MISSING_DS here: https://github.com/dotse/dnscheck
            """

            if line.startswith("WARNING [DNSSEC:MISSING_DS]"):
                infos.append("WARNING [DNSSEC:MISSING_DS]")
            else:
                warnings.append(line)

        if line.startswith("ERROR"):
            errors.append(line)

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

        # first line if language files are not installed
        if line.startswith("%s" % "INFO Did not find DNSKEY"):
            log.info(line)
            errors.append(line)
        if line.startswith("%s" % "INFO [DNSSEC:DNSKEY_NOT_FOUND]"):
            log.info(line)
            errors.append(line)

        # Why are the following upgraded? There is no explanation for this.
        # translations for the english language files
        # When NO DS is found, a warning will already be present in the output.
        # WARNING [DNSSEC:MISSING_DS]
        # SIDN ‐ If the parent has a DS record, the child must support DNSSEC (DNSSEC:NO_DS_FOUND).
        # https://gtldresult.icann.org/applicationstatus/applicationdetails:downloadattachment/12382?t:ac=915
        # All municipalities in NL that currently have imperfect DNS have the NO_DS_FOUND error.
        # The warning will be suppressed, as the parent can be checked for a correct DS.
        # you can also see this behavior in DNSVIZ, everything has a DS, except the child. And that is fine.

        # It's not clear if this really is a problematic warning.
        # if line.startswith("%s" % "INFO Did not find DS record"):
        #     log.info(line)
        #     errors.append(line)
        # if line.startswith("%s" % "INFO [DNSSEC:NO_DS_FOUND]"):
        #     log.info(line)
        #     errors.append(line)

        if line.startswith("%s" % "INFO Authenticated denial records not found"):
            log.info(line)
            errors.append(line)

        if line.startswith("%s" % "INFO No DNSKEY(s) found at child"):
            log.info(line)
            errors.append(line)

        # NSEC_NOT_FOUND can still mean NSEC3PARAM_FOUND and NSEC3_ITERATIONS_OK
        # so we don't need to check on this NSEC parameter
        # if line.startswith("%s" % "INFO [DNSSEC:NSEC_NOT_FOUND]"):
        #     log.info(line)
        #     errors.append(line)

        # if line.startswith("%s" % "INFO [DNSSEC:SKIPPED_NO_KEYS]"):
        #     log.info(line)
        #     errors.append(line)

    highest_level = "ERROR" if errors else "WARNING" if warnings else "INFO" if infos else "NONE"

    if highest_level == "NONE":
        raise ValueError("Did not correctly parse DNSSCAN result string. %s " % result)

    relevant_strings = []

    # upgrade relevant to the highest level by overwriting previous levels.
    if infos:
        relevant_strings = infos
    if warnings:
        relevant_strings = warnings
    if errors:
        relevant_strings = errors

    # log.debug("Relevant:")
    # log.debug(relevant_strings)

    return highest_level, relevant_strings
