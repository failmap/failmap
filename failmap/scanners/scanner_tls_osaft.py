import json
import logging
import platform
import subprocess
from datetime import datetime, timedelta

import pytz
from celery import Task, group
from django.conf import settings

from failmap.celery import app
from failmap.organizations.models import Organization, Url
from failmap.scanners.models import Endpoint
from failmap.scanners.timeout import timeout
from failmap.scanners.tls_scan_manager import TlsScanManager

from .scanner import allowed_to_scan, q_configurations_to_scan

log = logging.getLogger(__package__)

"""
This scanner currently uses:
- Linux commands
- O-Saft
- gawk
- GO (external scripts)
- cert-chain-resolver


Note: the goal for qualys is to add as many external (non humanly possible) resources as possible to have the
competitive edge. Therefore their scans will probably deviate for a few percent from "simpler" scans such as ours.
Qualys grading: https://community.qualys.com/docs/DOC-6321-ssl-labs-grading-2018
Older grading: https://github.com/ssllabs/research/wiki/SSL-Server-Rating-Guide


Uses O-SAFT and a number of external scripts to perform complete validation of TLS/SSL akin to SSL Labs.

Documentation:
https://www.owasp.org/index.php/O-Saft/Documentation#--trace-key

O-Saft is a really great tool, and misses a few things. Those gaps have been filled with:
- cert-chain-resolver, which checks the certificate chain.
- ticketbleed (test_cve_2016_9244), using a go script
- ?? padding oracle cve_2016_2107, using a go script (LuckyNegative20)
- todo: nmap os detection: this is required to get an idea if OpenSSL or another piece of software is used?

Alternatives could be:
sslscan: which also does not provide a general rating. But O-Saft has a better understanding of ciphers etc. Easier.
sslyze: doesn't give any conclusions. It does not show if a certificate has expired.
sslscan: compiles against an tls library that is able to test ssl2 and such. That is much better.
sslscan is easier to install via a package manager (does that do all scans?)

This scanner will scan TLS on all ports and will find many of the most common weaknesses.
O-Saft also able to check starttls on ftp, imap, irc, ldap, pop3, smtp, mysql, xmpp, postgres.
"""

"""
Implementation / Grading specification
These are the grades used in SSL Labs

Detail:                                    Grade:          In SslScan:                   Implemented    O-Saft  Imp.
SSLv2                                      F (set)         Yes (as SSlv2 support)                  Y    Y       Y
SSLv3                                      B (set)         Yes (as SSlv3 support)                  Y    Y       Y
Not using the latest TLS v1.2              C (cap)         Yes (in cypher suites)                  Y    Y       Y
Poodle (SSL3)                              C (cap)         Yes (CBC in cipher)                     Y    Y       ?
Poodle SSL3 = C                                                                                    Y    ?
Poodle TLS = F                                                                                     Y    ?
Crime attack (no compression + more)       C (cap)         Yes                                     Y    Y       Y
Heartbleed tls 0, 1, 2                     F (set)         Yes                                     Y    Y       Y
Insecure Session renegotation /MITM        F (set)         Yes                                     Y    Y       Y

No Trust due to Expiration                 T (set)         Yes, in Certificate                     Y    Y       Y
No Trust due to Self Signed                T (set)         Yes, in Certificate                     Y    Y       Y
Certificate name mismatch                  T (set)         Yes, in Certificate                     Y    ?       ?

Insecure Diffie Helman exchange (logjam)   F (set)         Yes, in supported cyphers               Y    Y       Y
Weak Diffie Helman                         B (cap)         Yes                                     Y    ?       ?

RC4 Cipher, but only older protocols       B (cap)         Yes                                     Y    ?       ?
RC4 Cipher, with modern protocols 1.2, 1.1 C (cap)         Yes                                     Y    Y       Y

Anonymous Ciphers                          F               Yes (ADH, AECDH)                        Y    Y       No aecdh

Insecure Cipher Suites                     F (set)         Yes, weak bits                          Y    Y       Y
                                                           Partial, some known weak ciphers        P            Y

512 bit export suites (Freak attack)       F               Yes, in cipher suites, EXP              Y    Y       Y

OpenSSl Padding Oracle                     F (set)         No, use FiloScottile tool requires GO(!)Y    -       Y
Ticketbleed                                Y               No, use other script. (see vendor dir)  Y    -       Y

64-bit block cipher (3DES / DES / RC2 / IDEA)
with modern protocols                      C (cap)         Yes, in cipher suites                   P    -


Certificate Chain Incomplete               B (cap)         Not determined, No. Gets only only 1.        -       Nearly
                                                           Use cert chain resolver.
To check: https://github.com/zakjan/cert-chain-resolver/


Revoked                                    F               No, requires revocation list.
Distrust in modern browsers (aka using revoked certificates) - This is a warning.
                                           T               Issue name against revocation list.
                                                           Spec StartCom + WoCom

Drown (similar key, using ssl2 elsehwere)  F               No, requires key database + updating.        Y (locally) Y
TLS 1.3?                                   ?               No (depends on openssl version?)
Forward Secrecy                            ?               Not determined, No. Not rated also.

sslscan (around line 1600):
https://github.com/rbsec/sslscan/blob/master/sslscan.c

Ticketbleed:
https://gist.github.com/FiloSottile/fc7822b1f5b475a25e58d77d1b394860

64 bit blocks:
https://sweet32.info/

LuckyNegative20:
https://blog.cloudflare.com/yet-another-padding-oracle-in-openssl-cbc-ciphersuites/

Poodle:
https://github.com/huggablehacker/poodle-test

BEAST: todo. All clients have client side mitigation. Is purely client side. No points awarded for
it anymore. RC4 was a bigger problem.
BREACH: todo. Disable HTTP compression, which is mandatory already
              https://en.wikipedia.org/wiki/BREACH - Same as CRIME.

What we should have used: https://www.owasp.org/index.php/O-Saft ... nah

"""
osaft_JSON = settings.TOOLS['osaft']['json']
cert_chain_resolver = settings.TOOLS['TLS']['cert_chain_resolver'][platform.system()]


@app.task(queue="storage")
def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
) -> Task:
    """Compose taskset to scan specified endpoints.

    *This is an implementation of `compose_task`. For more documentation about this concept, arguments and concrete
    examples of usage refer to `compose_task` in `types.py`.*

    """

    if not allowed_to_scan("scanner_tls_qualys"):
        return group()

    # apply filter to organizations (or if no filter, all organizations)
    organizations = []
    if organizations_filter:
        organizations = Organization.objects.filter(**organizations_filter)

        urls = Url.objects.filter(
            q_configurations_to_scan(),
            is_dead=False,
            not_resolvable=False,
            organization__in=organizations,  # whem empty, no results...
            **urls_filter,
        ).order_by("?")
    else:
        urls = Url.objects.filter(
            q_configurations_to_scan(),
            is_dead=False,
            not_resolvable=False,
            **urls_filter,
        ).order_by("?")

    urls = list(set(urls))  # unique only

    if endpoints_filter:
        raise NotImplementedError('This scanner needs to be refactored to scan per endpoint.')

    if not urls:
        log.warning('Applied filters resulted in no urls, thus no tls scan tasks!')
        return group()

    log.info('Creating scan task for %s urls for %s organizations.', len(urls), len(organizations))

    # todo: IPv6 is not well supported in O-Saft... will be updated in the future. Let's see what it does now.
    # todo: find the O-Saft command for IPv6 scans.
    endpoints = Endpoint.objects.all().filter(url__in=urls, protocol="https", ip_version=4, is_dead=False)

    task = group(run_osaft_scan.s(endpoint.url.url, endpoint.port)
                 | ammend_unsuported_issues.s(endpoint.url.url, endpoint.port)
                 | determine_grade.s()
                 | store_grade.s(endpoint) for endpoint in endpoints)
    return task


def compare_results():
    """
    Gets the latest scan results from previously done qualys scans. So to make it easier to compare output and see if
    this scanner needs extra implementations (or that there are bugs in O-Saft).

    :return:
    """
    from failmap.scanners.models import TlsScan, TlsQualysScan
    tlsscans = TlsScan.objects.all().filter(last_scan_moment__gte=datetime.now(pytz.utc) - timedelta(days=7))
    checked_scans = 0
    different_scans = 0

    for tlsscan in tlsscans:
        checked_scans += 1
        # log.debug("comparing %s" % tlsscan)
        # get the most recent qualys scan, see if there are differences. If so: publish it with a qualys scan link.
        latest_qualys = TlsQualysScan.objects.all().filter(endpoint=tlsscan.endpoint).latest('last_scan_moment')

        if latest_qualys.qualys_rating != tlsscan.rating or \
                latest_qualys.qualys_rating_no_trust != tlsscan.rating_no_trust:
            different_scans += 1
            qualys_scan_url = "https://www.ssllabs.com/ssltest/analyze.html?d=%s&hideResults=on&latest" % \
                              tlsscan.endpoint.url.url
            qualys_scan_saved_url = "http://localhost:8000/admin/scanners/tlsqualysscan/%s/change/" % \
                                    latest_qualys.pk
            tlsscan_saved = "http://localhost:8000/admin/scanners/tlsscan/%s/change/" % tlsscan.pk
            log.info("Difference between Qualys and O-Saft detected on %s:%s. \n"
                     "Qualys: %s, O-Saft: %s\n"
                     "Qualys: %s, O-Saft: %s (without trust)\n"
                     "Qualys online:%s\n"
                     "Qualys database:%s\n"
                     "TlsScan database:%s \n\n" % (tlsscan.endpoint.url.url, tlsscan.endpoint.port,
                                                   latest_qualys.qualys_rating, tlsscan.rating,
                                                   latest_qualys.qualys_rating_no_trust, tlsscan.rating_no_trust,
                                                   qualys_scan_url, qualys_scan_saved_url, tlsscan_saved))
        else:
            log.info("%s:%s has the same rating." % (tlsscan.endpoint.url.url, tlsscan.endpoint.port))

    log.info("")
    log.info("Summary:")
    log.info("%5s hosts scanned." % checked_scans)
    log.info("%5s host differed." % different_scans)
    log.info("")
    log.info('comparison completed.')


@app.task(queue="scanners")
def run_osaft_scan(address, port):
    # we're expecting SNI running everywhere. So we cant connect on IP alone, an equiv of http "host-header" is required
    # We're not storing anything on the filesystem and expect no dependencies on the O-Saft system. All post-processing
    # is done on another machine.

    # --trace-key: adds a key to follow the specific commands: the labels then can change without affecting this script
    # --legacy=quick : makes sure we're getting the json in proper output
    # +check performs an extensive array of checks

    # owasp/o-saft --trace-key --legacy=quick +check https://faalkaart.nl
    # todo: determine call routine to O-Saft, docker is fine during development, but what during production?
    # todo: running O-Saft on a website without https (http://) makes O-Saft hang.
    log.info("Running osaft scan on %s:%s" % (address, port))
    # **WARNING: 048: additional commands in conjunction with '+check' are not supported; +'selfsigned' ignored
    o_saft_command = ['docker', 'run', '--rm', '-it',
                                'owasp/o-saft', '--trace-key', '--legacy=quick', '+check',
                                "%s:%s" % (address, port)]
    log.info("O-Saft command: %s" % o_saft_command)
    process = subprocess.Popen(o_saft_command,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (standardout, junk) = process.communicate()
    log.info("O-Saft output:")
    log.info(standardout)
    return standardout


# hooray for command injection from osaft output. If you can manipulate that, we're done :)
# you can do so at any point in for example the contents of the HSTS header. So this is a really insecure way of
# processing the output.
def gawk(string):
    # echo string | gawk -f contrib/JSON-array.awk
    # todo: is echo a command? And what about command injection otherwise?
    echo = subprocess.Popen(["echo", string], stdout=subprocess.PIPE)
    # todo: check that gawk is installed
    gawk = subprocess.Popen(["gawk", "-f", osaft_JSON], stdin=echo.stdout, stdout=subprocess.PIPE)
    echo.stdout.close()  # Allow p1 to receive a SIGPIPE if p2 exits.
    output, err = gawk.communicate()

    log.debug("gawk output:")
    log.debug(output)
    return output


@app.task(queue="scanners")
def ammend_unsuported_issues(osaft_report, address, port=443):
    """
    A scan takes about a minute to complete and can be run against any TLS website and many other services.
    :param address: string, internet address, not an url object(!)
    :param port: integer, port number.
    :return:
    """

    # todo: does O-Saft support hostnames and separate IP's? So you can test on IPv4 and IPv6?
    # todo: what about hangs? What is a timeout?
    # It's possible to run multiple scans at the same time, so we might do this in a batched approach.
    # but what if one of these things hangs? I suppose O-Saft has timeouts.
    lines = gawk(osaft_report)  # convert the raw output to a JSON array
    lines = lines.decode("utf-8")  # commands deliver byte strings, convert to something more easy
    lines = lines.splitlines()  # split the report in multiple lines, to inject findings
    lines = lines[:-1]  # make it possible to inject some other findings by removing the closing tag.

    log.debug('Running workaround scans to complete O-Saft')
    try:
        vulnerable = test_cve_2016_2107(address, port)
        string = '  {"typ": "check", "key": "CVE-2016-2107", "label": "Safe against CVE-2016-2107:", "value":"' + \
                 ("no (vulnerable)" if bool(vulnerable) else "yes") + '"},'
        lines.append(string)
    except TimeoutError:
        string = ' {"typ": "check", "key": "CVE-2016-2107", "label": "Safe against CVE-2016-2107:", "value":"unknown"},'
        lines.append(string)

    try:
        vulnerable = test_cve_2016_9244(address, port)
        string = '  {"typ": "check", "key": "CVE-2016-9244", "label": "Safe against CVE-2016-9244:", "value":"' + \
                 ("no (vulnerable)" if bool(vulnerable) else "yes") + '"},'
        lines.append(string)
    except TimeoutError:
        string = ' {"typ": "check", "key": "CVE-2016-9244", "label": "Safe against CVE-2016-9244:", "value":"unknown"},'
        lines.append(string)

    # todo: add cert-chain-resolver

    # Remove comma from last line, json is very picky
    lines[len(lines)-1] = lines[len(lines)-1][:-1]

    lines.append("]")  # close the injection
    lines = "".join(lines)  # make it one line so json can load it
    # log.debug(lines)
    report = json.loads(lines)
    # log.debug(report)
    return report


def trust_check(report, key, asserted_value, message_if_assertion_failed):
    for line in report:
        if line['key'] == key:
            if line['value'] != asserted_value:
                return {'trusted': False, 'message': message_if_assertion_failed,
                        'debug_key': line['key'], 'debug_value': line['value']}
            else:
                # empty values are not added to the list.
                # give back the correct value, for debugging purposes.
                return {'trusted': True, 'message': 'OK',
                        'debug_key': line['key'], 'debug_value': line['value']}


def security_check(report, key, asserted_value, grade_if_assertion_failed, message_if_assertion_failed):
    for line in report:
        if line['key'] == key:
            if line['value'] != asserted_value:
                return {'grade': grade_if_assertion_failed, 'message': message_if_assertion_failed,
                        'debug_key': line['key'], 'debug_value': line['value']}
            else:
                # empty values are not added to the list.
                # give back the correct value, for debugging purposes.
                return {'grade': '', 'message': 'OK',
                        'debug_key': line['key'], 'debug_value': line['value']}


def weak_cipher_check(report, grade_if_assertion_failed, message_if_assertion_failed):
    for line in report:
        if line['typ'] == 'cipher' and line['value'] == "weak" and line['label'] == "yes":
            return {'grade': grade_if_assertion_failed, 'message': message_if_assertion_failed,
                    'debug_key': line['key'], 'debug_value': line['value']}

    # not found
    # empty values are not added to the list.
    # give back the correct value, for debugging purposes.
    return {'grade': '', 'message': 'OK',
            'debug_key': 'no weak ciphers'}


def security_value(report, key):
    for line in report:
        if line['key'] == key:
            return line['value']


@app.task(queue="storage")
def determine_grade(report):
    """
    Use the docker build of OSaft, otherwise you'll be building SSL until you've met all dependencies.
    O-Saft very neatly performs a lot of checks that we don't have to do anymore ourselves, wrongly.

    :param report: json report from O-Saft with injections
    :return: two lists of grades.
    """

    if not report:
        return [], []

    # list of items wether the certificate can be trusted or not (has chain of trust etc)
    # if any of the is_trusted is False, then there is no trust, which affects the rating (instant F)
    is_trusted = []
    is_trusted.append(trust_check(report, "dates", "yes", "Certificate is not valid anymore."))
    is_trusted.append(trust_check(report, "selfsigned", "yes", "Certificate is self-signed, chain of trust missing."))
    is_trusted.append(trust_check(report, "expired", "yes", "Certificate is expired."))
    is_trusted.append(trust_check(report, "sha2signature", "yes", "Obsolete Signature algorithm used."))

    # todo: hostname check.
    # todo: see +hostname vs. +wildhost vs. +altname vs. +rfc_2818
    # O-Saft only supports a check on hostname == certificate's subject. But a browser will accept if the hostname is
    # in the alt-names, and it's also fine if a wildcard certificate is used.
    is_trusted.append(trust_check(report, "hostname", "yes", "Hostname and certificate do not match"))

    # Various security checks.
    # F-Class
    ratings = []
    ratings.append(security_check(report, "heartbleed", "yes", "F", "Server vulnerable to Heartbleed"))
    ratings.append(security_check(report, "cipher_null", "yes", "F", "NULL Cipher supported."))
    ratings.append(security_check(report, "renegotiation", "yes", "F",
                                  "Server does not support secure session renegotiation, "
                                  "a Man in the Middle attack is possible."))
    ratings.append(security_check(report, "freak", "yes", "F", "Server is vulnerable to FREAK attack."))
    ratings.append(security_check(report, "poodle", "yes", "F", "Vulnerable to CVE_2014_3566 (POOODLE)."))
    ratings.append(security_check(report, "sweet32", "yes", "F", "Vulnerable to Sweet32."))
    ratings.append(security_check(report, "lucky13", "yes", "F", "Vulnerable to Lucky 13."))
    ratings.append(security_check(report, "hassslv2", "yes", "F", "Insecure/Obsolete protocol supported (SSLv2)."))
    ratings.append(security_check(report, "hassslv3", "yes", "F", "Insecure/Obsolete protocol supported (SSLv3)."))
    ratings.append(security_check(report, "logjam", "yes", "F", "Vulnerable to Logjam."))
    ratings.append(security_check(report, "CVE-2016-2107", "yes", "F", "Vulnerable to CVE_2016_2107 (padding oracle)."))
    ratings.append(security_check(report, "CVE-2016-9244", "yes", "F", "Vulnerable to CVE_2016_9244 (ticketbleed)."))
    ratings.append(weak_cipher_check(report, "F", "Insecure ciphers supported."))
    # Beast is not awarded any rating in Qualys anymore, as being purely client-side.
    ratings.append(security_check(report, "crime", "yes", "F", "Vulnerable to CRIME attack, due to compression used."))
    # todo: robot ( and the new robot)
    ratings.append(security_check(report, "drown", "yes", "F", "Vulnerable to DROWN attack. If this certificate is "
                                                               "used elsewhere, they are also vulnerable."))

    # Todo: does O-Saft not check AECDH cipher usage? Or is that included.
    ratings.append(security_check(report, "cipher_adh", "yes", "F", "Anonymous (insecure) suites used."))

    # C-Class
    # This does not check for TLS 1.3, which will come. Or have to come.
    ratings.append(security_check(report, "hastls12", "yes", "C",
                                  "The safest TLS protocol TLSv1.2 is not yet supported."))

    # todo: signature size is private key strength??? Doesn't seem to be, probably need some other options next to check
    private_key_strength = security_value(report, "len_sigdump")  # 2048 bits
    if private_key_strength:
        private_key_strength = int(private_key_strength.split(" ")[0])
        if 1024 <= private_key_strength < 2048:
            ratings.append({"grade": "C", "message": "Certificate has a weak key strength. (>= 1024 < 2048)",
                            "debug_key": "len_sigdump", "debug_value": private_key_strength})
        if private_key_strength < 1024:
            ratings.append({"grade": "F", "message": "Certificate has a weak key. < 1024 bits",
                            "debug_key": "len_sigdump", "debug_value": private_key_strength})

    # Qualys checks where RC4 is supported:
    # C when RC4 in ['TLSv1.2', 'TLSv1.1']
    # B when RC4 in ['TLSv1.0', 'SSLv3', 'SSLv2']
    # Here we can only check if RC4 is used at all (and not at what protocol as with sslyze), but who wants RC4 anyway
    # todo: isn't there any difference? Should O-Saft support this?
    ratings.append(security_check(
        report, "rc4", "yes", "F", "RC4 is accepted and poses a weakness."))

    # Qualys checks for low bit ciphers in modern protocols. Specifically
    # ['3DES', 'RC4', 'IDEA', 'RC2'] in ['TLSv1.2', 'TLSv1.1', 'TLSv1.0'], if so:
    # ['C', 'Using old 64-bit block cipher(s) (3DES / DES / RC2 / IDEA) with modern protocols.']

    # B-Class
    # todo: certificate chain check

    # Unknown Class
    # These are weaknesses described in O-Saft but not directly visible in Qualys. All ratings below might mis-match
    # the qualys rating. This can turn out to be a misalignment (where this or qualys is stronger).
    ratings.append(security_check(
        report, "cipher_strong", "yes", "B", "Server does not prefer strongest encryption first."))

    # todo: check what these things do in qualys.
    """
    "key":"Target does not accept NULL ciphers:","label":"yes","value":"yes"},
      {"typ":"check","line":"341","key":"Target does not accept EXPORT ciphers:","label":"yes","value":"yes"},
      {"typ":"check","line":"342","key":"Target does not accept CBC ciphers:","label":"yes","value":"yes"},
      {"typ":"check","line":"343","key":"Target does not accept DES ciphers:","label":"yes","value":"yes"}
    """

    # todo: check on weak DH parameters, there is some info about it in the results
    # Weak diffie helman, now seen as 1024, might be > 768 < 2048?
    #   if cipher['dhebits'] and int(cipher['dhebits']) == 1024:
    #       ratings.append(['B', "Weak Diffie-Hellman parameters used."])
    #  if cipher['bits'] and int(cipher['bits']) < 56:
    #       ratings.append(['F', "Insecure ciphers used (low number of bits)."])

    if final_grade(ratings) == "?":

        # See if we can go for A+ when HSTS is implemented (i think https should be the default... oh well)
        """
          {"typ":"check","line":"408","key":"Target does not send STS in meta tag:","label":"yes","value":"yes"},
          {"typ":"check","line":"409","key":"Target sends STS header:","label":"yes","value":"yes"},
          {"typ":"check","line":"410","key":"Target sends STS and no Location header:","label":"yes","value":"yes"},
          {"typ":"check","line":"411","key":"Target sends STS and no Refresh header:","label":"yes","value":"yes"},
          {"typ":"check","line":"412","key":"Target sends STS header with proper max-age:","label":"no (31536000 = 365 d
          {"typ":"check","line":"413","key":"Target sends STS header with includeSubdomain:","label":"yes","value":"yes"
          {"typ":"check","line":"414","key":"STS max-age not reset:","label":"yes","value":"yes"},
          {"typ":"check","line":"415","key":"STS max-age less than one day:","label":"no (> 86400)","value":"no (> 86400
          {"typ":"check","line":"416","key":"STS max-age less than one month:","label":"no (> 2592000)","value":"no (> 2
          {"typ":"check","line":"417","key":"STS max-age less than one year:","label":"no (> 31536000)","value":"no (> 3
          {"typ":"check","line":"418","key":"STS max-age more than 18 weeks:","label":"yes","value":"yes"},
          {"typ":"check","line":"419","key":"STS max-age more than one year:","label":"no (< 99999999)","value":"no (< 9
          {"typ":"check","line":"420","key":"STS max-age < certificate's validity:","label":"no (1531304486 + 31536000 >
        """
        # HSTS is only sensible on the "final" site, so redirects we can ignore.
        if all([security_value(report, "hsts_sts") == "yes",
                security_value(report, "hsts_location") == "yes",
                security_value(report, "hsts_refresh") == "yes",
                security_value(report, "sts_maxage0d") == "yes"]) and (
                    security_value(report, "sts_maxage18") == "yes" or
                    security_value(report, "sts_maxagexy") == "yes"):
            ratings.append({'grade': 'A+', 'message': 'No weaknesses found, forces security by using HSTS.',
                            'debug_key': 'A+', 'debug_value': 'A+'})
        else:
            ratings.append({'grade': 'A', 'message': 'No weaknesses found', 'debug_key': 'A', 'debug_value': 'A'})

    return ratings, is_trusted, report


def final_grade(ratings):
    # Order from worst to best: F, C, B, A, A+
    grades = []
    for rating in ratings:
        if rating['grade']:
            grades.append(rating['grade'])

    if "F" in grades:
        return "F"

    if "C" in grades:
        return "C"

    if "B" in grades:
        return "B"

    if "A" in grades:
        return "A"

    if "A+" in grades:
        return "A+"

    return "?"


def final_trust(trust_ratings):
    for rating in trust_ratings:
        if not rating["trusted"]:
            return "T"

    return ""


def grade_report(ratings, trust_ratings, report_for_debugging=""):
    import os
    report = ""
    report += 'Trust:  %s (T is not trusted, no value is trusted)' % final_trust(trust_ratings) + os.linesep
    report += 'Rating: %s (F to A+, american school grades)' % final_grade(ratings) + os.linesep

    report += '-------------------------------------------------------------------' + os.linesep
    report += 'Trust' + os.linesep
    for rating in trust_ratings:
        report += "  %2s: %5s (%s)" % (rating['trusted'], rating['message'], rating['debug_key']) + os.linesep
    report += '' + os.linesep

    report += 'Vulnerabilities' + os.linesep
    for rating in ratings:
        report += "  %2s: %s (%s)" % (rating['grade'], rating['message'], rating['debug_key']) + os.linesep
    report += '' + os.linesep

    if report_for_debugging:
        log.debug("Complete Scanner output")
        for line in report_for_debugging:
            report += str(line) + os.linesep

    return report


# todo: what to do if there is no connection, what to do if connection fails etc...
# in that case no rating?
# todo: remove endpoint management from qualys scans. Qualys scans cannot kill or discover endpoints: only the
# discovery script can do that.


@app.task(queue="storage")
def store_grade(combined_ratings, endpoint):
    ratings, trust_ratings, report = combined_ratings

    trusted = final_trust(trust_ratings)
    grade = final_grade(ratings)

    # This is how qualys normally migrates the normal rating when there is trust.
    if trusted != "T":
        trusted = grade

    TlsScanManager.add_scan(endpoint, trusted, grade, "", grade_report(ratings, trust_ratings, report))


@timeout(3)
def test_cve_2016_2107(url, port):
    # The script will timeout sometimes.

    # writes to stderror by default.
    log.info("Testing test_cve_2016_2107")
    process = subprocess.Popen(['go', 'run', settings.TOOLS['TLS']['cve_2016_2107'], "%s:%s" % (url, port)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # get last word of first line. Can be true or false. Should only get one line.
    out, err = process.communicate()
    # print(out)
    # print(err)
    if "Vulnerable: true" in str(err) or "Vulnerable: true" in str(out):
        return True
    return False


@timeout(3)
def test_cve_2016_9244(url, port):
    # The script will timeout sometimes.
    log.info("Testing test_cve_2016_9244")
    process = subprocess.Popen(['go', 'run', settings.TOOLS['TLS']['cve_2016_9244'], "%s:%s" % (url, port)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = process.communicate()
    # print(out)
    if "is vulnerable to Ticketbleed" in str(err) or "is vulnerable to Ticketbleed" in str(out):
        return True
    return False


@timeout(10)
def cert_chain_is_complete(url, port):
    """
    Download cert:
    openssl s_client -showcerts -connect microsoft.com:443 </dev/null 2>/dev/null|openssl x509
    -outform PEM >microsoft.pem
    ./cert-chain-resolver microsoft.pem
    :param url:
    :param port:
    :return:
    """
    # pyflakes tool = settings.TOOLS['TLS']['cert_chain_resolver'][platform.system()]
    # openssl s_client -showcerts -connect microsoft.com:443 </dev/null 2>/dev/null|
    # openssl x509 -outform PEM >microsoft.pem

    # /Applications/XAMPP/xamppfiles/htdocs/faalkaart/test/cert-chain-resolver_darwin_amd64/cert-chain-resolver
    # process = subprocess.Popen(['openssl',
    #                             's_client',
    #                             '-showcerts',
    #                             '-connect', '%s:%s', ],
    #                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    raise NotImplementedError

# todo: create downloader for specific urls so we can easily harvest testcases


def testcase(filename, domain='example.com'):
    log.info(filename)
    rating, trust_rating = determine_grade('testcases/' + filename + '.xml')
    print(grade_report(rating, trust_rating))


def test_real(url='faalkaart.nl', port=443):
    report = run_osaft_scan(url, port)
    report = ammend_unsuported_issues(report, url, port)
    rating, trust_rating = determine_grade(report)
    print(grade_report(rating, trust_rating))


def test_determine_grade():
    # sslscan --show-certificate --xml=A7.xml support.url:443 1>/dev/null &

    testcase('sha1_selfsigned_expired')
    testcase('Fanon_cypers')
    testcase('F_notrust_signature_ssl2_poodle_DH_rc4_chain')
    testcase('F_padding_oracle_C_pooldle_weakdh_nofs')
    testcase('F_insecure_ciphers_C_64bit_block_cipher_B_rc4_B_chain')
    testcase('F_ssl2_C_poodle_B_weakdh_C_no12_B_RC4')
    testcase('F_ssl2_F_ciphers_F_FREAK_B_SSL3_etc')
    testcase('F_ticketbleed_paddingoracle')
    testcase('C_RC4_modern_C_64_bit_block_nofs')
    testcase('B_weak_dh')
    testcase('B_weakdh_B_RC4_older_protocols')
    testcase('B_weakdh_NoFS')
    testcase('T_notInTrustStore_lolchain')  # should be A.
    testcase('A1')
    testcase('A2')
    testcase('A3')
    testcase('A4')
    testcase('A5')
    testcase('A6')
    testcase('A7')
