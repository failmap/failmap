import json
import logging
import platform
import subprocess

from django.conf import settings

from failmap.celery import app
from failmap.scanners.models import Endpoint
from failmap.scanners.timeout import timeout

log = logging.getLogger(__package__)

"""
This scanner currently uses:
- Linux commands
- O-Saft
- gawk
- GO (external scripts)
- cert-chain-resolver



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
# ./o-saft.pl +check faalkaart.nl | gawk -f contrib/JSON-array.awk > faalkaart.osaft

osaft_JSON = settings.TOOLS['osaft']['json']
cert_chain_resolver = settings.TOOLS['TLS']['cert_chain_resolver'][platform.system()]


def scan_url(url):
    endpoints = Endpoint.objects.all().filter(url=url, protocol='https')
    for endpoint in endpoints:
        report = scan_endpoint(endpoint)
        rating, trust_rating = determine_grade(report, endpoint.url.url)
        store_grade(rating, trust_rating, endpoint)


@app.task(queue="scanners")
def scan_endpoint(endpoint, IPv6=False):
    return scan_address(endpoint.url.url, endpoint.port)


@timeout(60)
def run_osaft_scan(address, port):
    # we're expecting SNI running everywhere. So we cant connect on IP alone, an equiv of http "host-header" is required
    # We're not storing anything on the filesystem and expect no dependencies on the O-Saft system. All post-processing
    # is done on another machine.

    # --trace-key: adds a key to follow the specific commands: the labels then can change without affecting this script
    # --legacy=quick : makes sure we're getting the json in proper output
    # +check performs an extensive array of checks

    # owasp/o-saft --trace-key --legacy=quick +check https://faalkaart.nl
    # todo: determine call routine to O-Saft, docker is fine during development, but what during production?
    log.debug("Running osaft scan on %s:%s" % (address, port))
    process = subprocess.Popen(['docker', 'run', '--rm', '-it',
                                'owasp/o-saft', '--trace-key', '--legacy=quick', '+check', "%s:%s" % (address, port)],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (standardout, junk) = process.communicate()
    log.debug("Output:")
    log.debug(standardout)
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

    log.debug("Output:")
    log.debug(output)
    return output


def scan_address(address, port=443):
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

    report = run_osaft_scan(address, port)
    lines = gawk(report)  # convert the raw output to a JSON array
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

    # Todo: does O-Saft not check AECDH cipher usage? Or is that included.
    ratings.append(security_check(report, "cipher_adh", "yes", "F", "Anonymous (insecure) suites used."))

    # C-Class
    # This does not check for TLS 1.3, which will come. Or have to come.
    ratings.append(security_check(report, "hastls12", "yes", "C",
                                  "The safest TLS protocol TLSv1.2 is not yet supported."))
    ratings.append(security_check(report, "crime", "yes", "C", "Vulnerable to CRIME attack, due to compression used."))

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

    return ratings, is_trusted


def final_grade(ratings):
    # Order from worst to best: F, C, B, A, A+
    grades = []
    for rating in ratings:
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


def debug_grade(ratings, trust_ratings):
    log.debug('Trust:  %s (T is not trusted, no value is trusted)' % final_trust(trust_ratings))
    log.debug('Rating: %s (F to A+, american school grades)' % final_grade(ratings))

    log.debug('-------------------------------------------------------------------')
    log.debug('Trust')
    for rating in trust_ratings:
        log.debug("  %2s: %5s (%s)" % (rating['trusted'], rating['message'], rating['debug_key']))
    log.debug('')

    log.debug('Vulnerabilities')
    for rating in ratings:
        log.debug("  %2s: %s (%s)" % (rating['grade'], rating['message'], rating['debug_key']))
    log.debug('')


# todo: what to do if there is no connection, what to do if connection fails etc...
# in that case no rating?

@app.task(queue="storage")
def store_grade(ratings, trust_ratings, endpoint):
    trusted = final_trust(trust_ratings)
    grade = final_grade(ratings)

    if trusted != "T":
        trusted = grade

    # qualysscanmanager to store the rating.

    # clone of the qualys table. We're not doing the same management here as in the qualys thing.
    # we'll use the https-discovery to see where TLS is used, and then use this script.
    # which makes it much easier to handle issues.


@timeout(3)
def test_cve_2016_2107(url, port):
    # The script will timeout sometimes.

    # writes to stderror by default.
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
    rating, trust_rating = determine_grade('testcases/' + filename + '.xml', domain)
    debug_grade(rating, trust_rating)


def test_real(url='faalkaart.nl', port=443):
    report_path = scan_address(url, port)
    rating, trust_rating = determine_grade(report_path, url)
    debug_grade(rating, trust_rating)


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


def get_sample_report():
    # removed the ; at the end
    # true and false are lowercase
    # the last comma is not valid, after the last true/false

    return """[
  {"typ":"hint","line":"1","key":"1","label":"1","value":"!!Hint: --force-openssl can be used to disable this check"},
  {"typ":"hint","line":"2","key":"2","label":"2","value":"!!Hint: --no-alpn can be used to disable this check"},
  {"typ":"hint","line":"3","key":"3","label":"3","value":"!!Hint: --no-npn can be used to disable this check"},
  {"typ":"warning","line":"4","key":"1","label":"4","value":"**WARNING: 145: openssl s_client does not support '-fallbac
  {"typ":"warning","line":"5","key":"2","label":"5","value":"**WARNING: 145: openssl s_client does not support '-psk_ide
  {"typ":"warning","line":"6","key":"3","label":"6","value":"**WARNING: 145: openssl s_client does not support '-psk'; P
  {"typ":"warning","line":"7","key":"4","label":"7","value":"**WARNING: 145: openssl s_client does not support '-serveri
  {"typ":"warning","line":"8","key":"5","label":"8","value":"**WARNING: 143: SSL version 'SSLv2': not supported by Net::
  {"typ":"warning","line":"9","key":"6","label":"9","value":"**WARNING: 143: SSL version 'SSLv3': not supported by Net::
  {"typ":"warning","line":"10","key":"7","label":"10","value":"**WARNING: 143: SSL version 'TLSv13': not supported by Ne
  {"typ":"warning","line":"11","key":"8","label":"11","value":"**WARNING: 066: 7 data and check outputs are disbaled due
  {"typ":"hint","line":"12","key":"4","label":"12","value":"!!Hint: use  '--v'  for more information"},
  {"typ":"hint","line":"13","key":"5","label":"13","value":"!!Hint: do not use '--ignore-out=*' or '--no-out=*' options"
  {"typ":"info","line":"14","key":"Given hostname:","label":"faalkaart.nl","value":"faalkaart.nl"},
  {"typ":"info","line":"15","key":"IP for given hostname:","label":"37.97.164.72","value":"37.97.164.72"},
  {"typ":"info","line":"16","key":"Reverse resolved hostname:","label":"37-97-164-72.colo.transip.net","value":"37-97-16
  {"typ":"info","line":"17","key":"DNS entries for given hostname:","label":"37.97.164.72 37-97-164-72.colo.transip.net;
  {"typ":"cipher","line":"18","key":"ECDHE-ECDSA-CHACHA20-POLY1305","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"19","key":"ECDHE-RSA-CHACHA20-POLY1305","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"20","key":"DHE-RSA-CHACHA20-POLY1305","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"21","key":"ECDHE-RSA-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"22","key":"ECDHE-ECDSA-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"23","key":"ECDHE-RSA-AES256-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"24","key":"ECDHE-ECDSA-AES256-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"25","key":"ECDHE-RSA-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"26","key":"ECDHE-ECDSA-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"27","key":"DHE-DSS-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"28","key":"DHE-RSA-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"29","key":"DHE-RSA-AES256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"30","key":"DHE-DSS-AES256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"31","key":"DHE-RSA-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"32","key":"DHE-DSS-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"warning","line":"33","key":"9","label":"33","value":"**WARNING: 016: undefined cipher description for 'GOST201
  {"typ":"info","line":"34","key":"GOST2012256-GOST89-GOST89","label":"no","value":"<<undef>>"},
  {"typ":"cipher","line":"35","key":"DHE-RSA-CAMELLIA256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"36","key":"DHE-DSS-CAMELLIA256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"37","key":"DHE-RSA-CAMELLIA256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"38","key":"DHE-DSS-CAMELLIA256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"39","key":"GOST2001-GOST89-GOST89","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"40","key":"AECDH-AES256-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"41","key":"ADH-AES256-GCM-SHA384","label":"no","value":"weak"},
  {"typ":"cipher","line":"42","key":"ADH-AES256-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"43","key":"ADH-AES256-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"44","key":"ADH-CAMELLIA256-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"45","key":"ADH-CAMELLIA256-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"46","key":"ECDH-RSA-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"47","key":"ECDH-ECDSA-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"48","key":"ECDH-RSA-AES256-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"49","key":"ECDH-ECDSA-AES256-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"50","key":"ECDH-RSA-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"51","key":"ECDH-ECDSA-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"52","key":"AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"53","key":"AES256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"54","key":"AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"55","key":"CAMELLIA256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"56","key":"CAMELLIA256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"57","key":"ECDHE-RSA-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"58","key":"ECDHE-ECDSA-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"59","key":"ECDHE-RSA-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"60","key":"ECDHE-ECDSA-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"61","key":"ECDHE-RSA-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"62","key":"ECDHE-ECDSA-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"63","key":"DHE-DSS-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"64","key":"DHE-RSA-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"65","key":"DHE-RSA-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"66","key":"DHE-DSS-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"67","key":"DHE-RSA-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"68","key":"DHE-DSS-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"69","key":"DHE-RSA-CAMELLIA128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"70","key":"DHE-DSS-CAMELLIA128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"71","key":"DHE-RSA-CAMELLIA128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"72","key":"DHE-DSS-CAMELLIA128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"73","key":"AECDH-AES128-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"74","key":"ADH-AES128-GCM-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"75","key":"ADH-AES128-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"76","key":"ADH-AES128-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"77","key":"ADH-CAMELLIA128-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"78","key":"ADH-CAMELLIA128-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"79","key":"ECDH-RSA-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"80","key":"ECDH-ECDSA-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"81","key":"ECDH-RSA-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"82","key":"ECDH-ECDSA-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"83","key":"ECDH-RSA-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"84","key":"ECDH-ECDSA-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"85","key":"AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"86","key":"AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"87","key":"AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"88","key":"CAMELLIA128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"89","key":"CAMELLIA128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"90","key":"ECDHE-RSA-RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"91","key":"ECDHE-ECDSA-RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"92","key":"AECDH-RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"93","key":"ADH-RC4-MD5","label":"no","value":"weak"},
  {"typ":"cipher","line":"94","key":"ECDH-RSA-RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"95","key":"ECDH-ECDSA-RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"96","key":"RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"97","key":"RC4-MD5","label":"no","value":"weak"},
  {"typ":"cipher","line":"98","key":"ECDHE-RSA-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"99","key":"ECDHE-ECDSA-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"100","key":"EDH-RSA-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"101","key":"EDH-DSS-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"102","key":"AECDH-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"103","key":"ADH-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"104","key":"ECDH-RSA-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"105","key":"ECDH-ECDSA-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"106","key":"DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"107","key":"EDH-RSA-DES-CBC-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"108","key":"EDH-DSS-DES-CBC-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"109","key":"ADH-DES-CBC-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"110","key":"DES-CBC-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"111","key":"ECDHE-RSA-NULL-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"112","key":"ECDHE-ECDSA-NULL-SHA","label":"no","value":"weak"},
  {"typ":"warning","line":"113","key":"10","label":"113","value":"**WARNING: 016: undefined cipher description for 'GOST
  {"typ":"info","line":"114","key":"GOST2012256-NULL-STREEBOG256","label":"no","value":"<<undef>>"},
  {"typ":"cipher","line":"115","key":"GOST2001-NULL-GOST94","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"116","key":"AECDH-NULL-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"117","key":"ECDH-RSA-NULL-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"118","key":"ECDH-ECDSA-NULL-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"119","key":"NULL-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"120","key":"NULL-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"121","key":"NULL-MD5","label":"no","value":"weak"},
  {"typ":"cipher","line":"122","key":"ECDHE-ECDSA-CHACHA20-POLY1305","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"123","key":"ECDHE-RSA-CHACHA20-POLY1305","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"124","key":"DHE-RSA-CHACHA20-POLY1305","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"125","key":"ECDHE-RSA-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"126","key":"ECDHE-ECDSA-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"127","key":"ECDHE-RSA-AES256-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"128","key":"ECDHE-ECDSA-AES256-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"129","key":"ECDHE-RSA-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"130","key":"ECDHE-ECDSA-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"131","key":"DHE-DSS-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"132","key":"DHE-RSA-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"133","key":"DHE-RSA-AES256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"134","key":"DHE-DSS-AES256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"135","key":"DHE-RSA-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"136","key":"DHE-DSS-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"warning","line":"137","key":"11","label":"137","value":"**WARNING: 016: undefined cipher description for 'GOST
  {"typ":"info","line":"138","key":"GOST2012256-GOST89-GOST89","label":"no","value":"<<undef>>"},
  {"typ":"cipher","line":"139","key":"DHE-RSA-CAMELLIA256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"140","key":"DHE-DSS-CAMELLIA256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"141","key":"DHE-RSA-CAMELLIA256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"142","key":"DHE-DSS-CAMELLIA256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"143","key":"GOST2001-GOST89-GOST89","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"144","key":"AECDH-AES256-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"145","key":"ADH-AES256-GCM-SHA384","label":"no","value":"weak"},
  {"typ":"cipher","line":"146","key":"ADH-AES256-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"147","key":"ADH-AES256-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"148","key":"ADH-CAMELLIA256-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"149","key":"ADH-CAMELLIA256-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"150","key":"ECDH-RSA-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"151","key":"ECDH-ECDSA-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"152","key":"ECDH-RSA-AES256-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"153","key":"ECDH-ECDSA-AES256-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"154","key":"ECDH-RSA-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"155","key":"ECDH-ECDSA-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"156","key":"AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"157","key":"AES256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"158","key":"AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"159","key":"CAMELLIA256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"160","key":"CAMELLIA256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"161","key":"ECDHE-RSA-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"162","key":"ECDHE-ECDSA-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"163","key":"ECDHE-RSA-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"164","key":"ECDHE-ECDSA-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"165","key":"ECDHE-RSA-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"166","key":"ECDHE-ECDSA-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"167","key":"DHE-DSS-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"168","key":"DHE-RSA-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"169","key":"DHE-RSA-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"170","key":"DHE-DSS-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"171","key":"DHE-RSA-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"172","key":"DHE-DSS-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"173","key":"DHE-RSA-CAMELLIA128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"174","key":"DHE-DSS-CAMELLIA128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"175","key":"DHE-RSA-CAMELLIA128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"176","key":"DHE-DSS-CAMELLIA128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"177","key":"AECDH-AES128-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"178","key":"ADH-AES128-GCM-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"179","key":"ADH-AES128-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"180","key":"ADH-AES128-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"181","key":"ADH-CAMELLIA128-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"182","key":"ADH-CAMELLIA128-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"183","key":"ECDH-RSA-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"184","key":"ECDH-ECDSA-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"185","key":"ECDH-RSA-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"186","key":"ECDH-ECDSA-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"187","key":"ECDH-RSA-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"188","key":"ECDH-ECDSA-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"189","key":"AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"190","key":"AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"191","key":"AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"192","key":"CAMELLIA128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"193","key":"CAMELLIA128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"194","key":"ECDHE-RSA-RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"195","key":"ECDHE-ECDSA-RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"196","key":"AECDH-RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"197","key":"ADH-RC4-MD5","label":"no","value":"weak"},
  {"typ":"cipher","line":"198","key":"ECDH-RSA-RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"199","key":"ECDH-ECDSA-RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"200","key":"RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"201","key":"RC4-MD5","label":"no","value":"weak"},
  {"typ":"cipher","line":"202","key":"ECDHE-RSA-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"203","key":"ECDHE-ECDSA-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"204","key":"EDH-RSA-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"205","key":"EDH-DSS-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"206","key":"AECDH-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"207","key":"ADH-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"208","key":"ECDH-RSA-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"209","key":"ECDH-ECDSA-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"210","key":"DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"211","key":"EDH-RSA-DES-CBC-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"212","key":"EDH-DSS-DES-CBC-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"213","key":"ADH-DES-CBC-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"214","key":"DES-CBC-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"215","key":"ECDHE-RSA-NULL-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"216","key":"ECDHE-ECDSA-NULL-SHA","label":"no","value":"weak"},
  {"typ":"warning","line":"217","key":"12","label":"217","value":"**WARNING: 016: undefined cipher description for 'GOST
  {"typ":"info","line":"218","key":"GOST2012256-NULL-STREEBOG256","label":"no","value":"<<undef>>"},
  {"typ":"cipher","line":"219","key":"GOST2001-NULL-GOST94","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"220","key":"AECDH-NULL-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"221","key":"ECDH-RSA-NULL-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"222","key":"ECDH-ECDSA-NULL-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"223","key":"NULL-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"224","key":"NULL-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"225","key":"NULL-MD5","label":"no","value":"weak"},
  {"typ":"cipher","line":"226","key":"ECDHE-ECDSA-CHACHA20-POLY1305","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"227","key":"ECDHE-RSA-CHACHA20-POLY1305","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"228","key":"DHE-RSA-CHACHA20-POLY1305","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"229","key":"ECDHE-RSA-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"230","key":"ECDHE-ECDSA-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"231","key":"ECDHE-RSA-AES256-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"232","key":"ECDHE-ECDSA-AES256-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"233","key":"ECDHE-RSA-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"234","key":"ECDHE-ECDSA-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"235","key":"DHE-DSS-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"236","key":"DHE-RSA-AES256-GCM-SHA384","label":"yes","value":"HIGH"},
  {"typ":"cipher","line":"237","key":"DHE-RSA-AES256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"238","key":"DHE-DSS-AES256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"239","key":"DHE-RSA-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"240","key":"DHE-DSS-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"warning","line":"241","key":"13","label":"241","value":"**WARNING: 016: undefined cipher description for 'GOST
  {"typ":"info","line":"242","key":"GOST2012256-GOST89-GOST89","label":"no","value":"<<undef>>"},
  {"typ":"cipher","line":"243","key":"DHE-RSA-CAMELLIA256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"244","key":"DHE-DSS-CAMELLIA256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"245","key":"DHE-RSA-CAMELLIA256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"246","key":"DHE-DSS-CAMELLIA256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"247","key":"GOST2001-GOST89-GOST89","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"248","key":"AECDH-AES256-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"249","key":"ADH-AES256-GCM-SHA384","label":"no","value":"weak"},
  {"typ":"cipher","line":"250","key":"ADH-AES256-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"251","key":"ADH-AES256-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"252","key":"ADH-CAMELLIA256-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"253","key":"ADH-CAMELLIA256-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"254","key":"ECDH-RSA-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"255","key":"ECDH-ECDSA-AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"256","key":"ECDH-RSA-AES256-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"257","key":"ECDH-ECDSA-AES256-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"258","key":"ECDH-RSA-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"259","key":"ECDH-ECDSA-AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"260","key":"AES256-GCM-SHA384","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"261","key":"AES256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"262","key":"AES256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"263","key":"CAMELLIA256-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"264","key":"CAMELLIA256-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"265","key":"ECDHE-RSA-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"266","key":"ECDHE-ECDSA-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"267","key":"ECDHE-RSA-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"268","key":"ECDHE-ECDSA-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"269","key":"ECDHE-RSA-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"270","key":"ECDHE-ECDSA-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"271","key":"DHE-DSS-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"272","key":"DHE-RSA-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"273","key":"DHE-RSA-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"274","key":"DHE-DSS-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"275","key":"DHE-RSA-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"276","key":"DHE-DSS-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"277","key":"DHE-RSA-CAMELLIA128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"278","key":"DHE-DSS-CAMELLIA128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"279","key":"DHE-RSA-CAMELLIA128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"280","key":"DHE-DSS-CAMELLIA128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"281","key":"AECDH-AES128-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"282","key":"ADH-AES128-GCM-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"283","key":"ADH-AES128-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"284","key":"ADH-AES128-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"285","key":"ADH-CAMELLIA128-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"286","key":"ADH-CAMELLIA128-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"287","key":"ECDH-RSA-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"288","key":"ECDH-ECDSA-AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"289","key":"ECDH-RSA-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"290","key":"ECDH-ECDSA-AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"291","key":"ECDH-RSA-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"292","key":"ECDH-ECDSA-AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"293","key":"AES128-GCM-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"294","key":"AES128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"295","key":"AES128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"296","key":"CAMELLIA128-SHA256","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"297","key":"CAMELLIA128-SHA","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"298","key":"ECDHE-RSA-RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"299","key":"ECDHE-ECDSA-RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"300","key":"AECDH-RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"301","key":"ADH-RC4-MD5","label":"no","value":"weak"},
  {"typ":"cipher","line":"302","key":"ECDH-RSA-RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"303","key":"ECDH-ECDSA-RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"304","key":"RC4-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"305","key":"RC4-MD5","label":"no","value":"weak"},
  {"typ":"cipher","line":"306","key":"ECDHE-RSA-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"307","key":"ECDHE-ECDSA-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"308","key":"EDH-RSA-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"309","key":"EDH-DSS-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"310","key":"AECDH-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"311","key":"ADH-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"312","key":"ECDH-RSA-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"313","key":"ECDH-ECDSA-DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"314","key":"DES-CBC3-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"315","key":"EDH-RSA-DES-CBC-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"316","key":"EDH-DSS-DES-CBC-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"317","key":"ADH-DES-CBC-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"318","key":"DES-CBC-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"319","key":"ECDHE-RSA-NULL-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"320","key":"ECDHE-ECDSA-NULL-SHA","label":"no","value":"weak"},
  {"typ":"warning","line":"321","key":"14","label":"321","value":"**WARNING: 016: undefined cipher description for 'GOST
  {"typ":"info","line":"322","key":"GOST2012256-NULL-STREEBOG256","label":"no","value":"<<undef>>"},
  {"typ":"cipher","line":"323","key":"GOST2001-NULL-GOST94","label":"no","value":"HIGH"},
  {"typ":"cipher","line":"324","key":"AECDH-NULL-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"325","key":"ECDH-RSA-NULL-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"326","key":"ECDH-ECDSA-NULL-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"327","key":"NULL-SHA256","label":"no","value":"weak"},
  {"typ":"cipher","line":"328","key":"NULL-SHA","label":"no","value":"weak"},
  {"typ":"cipher","line":"329","key":"NULL-MD5","label":"no","value":"weak"},
  {"typ":"info","line":"330","key":"TLSv1:","label":"0   0   0   0   0   0","value":"0   0   0   0   0   0"},
  {"typ":"info","line":"331","key":"TLSv11:","label":"0   0   0   0   0   0","value":"0   0   0   0   0   0"},
  {"typ":"info","line":"332","key":"TLSv12:","label":"1   0   0   0   1   1","value":"1   0   0   0   1   1"},
  {"typ":"cipher","line":"333","key":"Selected Cipher:","label":"ECDHE-RSA-AES256-GCM-SHA384 HIGH","value":"ECDHE-RSA-AE
  {"typ":"warning","line":"334","key":"15","label":"334","value":"**WARNING: 631: protocol '' does not match; no selecte
  {"typ":"check","line":"335","key":"Target selects strongest cipher:","label":"yes","value":"yes"},
  {"typ":"check","line":"336","key":"Target does not support SSLv2:","label":"no (<<N/A as --no-SSLv2 in use>>)","value"
  {"typ":"check","line":"337","key":"Target does not support SSLv3:","label":"no (<<N/A as --no-SSLv3 in use>>)","value"
  {"typ":"check","line":"338","key":"Target supports TLSv1.2:","label":"yes","value":"yes"},
  {"typ":"check","line":"339","key":"Target does not accept NULL ciphers:","label":"yes","value":"yes"},
  {"typ":"check","line":"340","key":"Target does not accept ADH ciphers:","label":"yes","value":"yes"},
  {"typ":"check","line":"341","key":"Target does not accept EXPORT ciphers:","label":"yes","value":"yes"},
  {"typ":"check","line":"342","key":"Target does not accept CBC ciphers:","label":"yes","value":"yes"},
  {"typ":"check","line":"343","key":"Target does not accept DES ciphers:","label":"yes","value":"yes"},
  {"typ":"check","line":"344","key":"Target does not accept RC4 ciphers:","label":"yes","value":"yes"},
  {"typ":"check","line":"345","key":"Target supports EDH ciphers:","label":"yes","value":"yes"},
  {"typ":"check","line":"346","key":"Target supports PFS (selected cipher):","label":"yes","value":"yes"},
  {"typ":"check","line":"347","key":"Target supports PFS (all ciphers):","label":"no ( )","value":"no ( )"},
  {"typ":"check","line":"348","key":"Target DH Parameter >= 512 bits:","label":"no (<<openssl did not return DH Paramter
  {"typ":"check","line":"349","key":"Target DH Parameter >= 2048 bits:","label":"no (<<openssl did not return DH Paramte
  {"typ":"check","line":"350","key":"Target DH Parameter >= 256 bits (ECDH):","label":"no (<<openssl did not return DH P
  {"typ":"check","line":"351","key":"Target DH Parameter >= 512 bits (ECDH):","label":"no (<<openssl did not return DH P
  {"typ":"check","line":"352","key":"Target is strict TR-02102-2 compliant:","label":"no ( <<not TLSv12>>)","value":"no
  {"typ":"check","line":"353","key":"Target is  lazy  TR-02102-2 compliant:","label":"no ( <<not TLSv12>>)","value":"no
  {"typ":"check","line":"354","key":"Connection is safe against BEAST attack (any cipher):","label":"no ( <<N/A as --no-
  {"typ":"check","line":"355","key":"Connection is safe against BREACH attack:","label":"no (<<NOT YET IMPLEMENTED>>)","
  {"typ":"check","line":"356","key":"Connection is safe against CCS Injection attack:","label":"no (<<NOT YET IMPLEMENTE
  {"typ":"check","line":"357","key":"Connection is safe against CRIME attack:","label":"yes","value":"yes"},
  {"typ":"check","line":"358","key":"Connection is safe against DROWN attack:","label":"no (<<N/A as --no-SSLv2 in use>>
  {"typ":"hint","line":"359","key":"6","label":"359","value":"!!Hint: checks only if the target server itself is vulnera
  {"typ":"check","line":"360","key":"Connection is safe against FREAK attack:","label":"yes","value":"yes"},
  {"typ":"check","line":"361","key":"Connection is safe against Heartbleed attack:","label":"yes","value":"yes"},
  {"typ":"check","line":"362","key":"Connection is safe against Logjam attack:","label":"no (<<openssl did not return DH
  {"typ":"check","line":"363","key":"Connection is safe against Lucky 13 attack:","label":"yes","value":"yes"},
  {"typ":"check","line":"364","key":"Connection is safe against POODLE attack:","label":"no (<<N/A as --no-SSLv3 in use>
  {"typ":"check","line":"365","key":"Connection is safe against RC4 attack:","label":"yes","value":"yes"},
  {"typ":"check","line":"366","key":"Connection is safe against ROBOT attack:","label":"yes","value":"yes"},
  {"typ":"hint","line":"367","key":"7","label":"367","value":"!!Hint: checks only if the target offers ciphers vulnerabl
  {"typ":"check","line":"368","key":"Connection is safe against Sweet32 attack:","label":"yes","value":"yes"},
  {"typ":"check","line":"369","key":"Connection is not based on SNI:","label":"yes","value":"yes"},
  {"typ":"check","line":"370","key":"Connected hostname equals certificate's Subject:","label":"no (faalkaart.nl <> faal
  {"typ":"check","line":"371","key":"Given hostname is same as reverse resolved hostname:","label":"no (faalkaart.nl <>
  {"typ":"check","line":"372","key":"Certificate has Certification Practice Statement:","label":"yes","value":"yes"},
  {"typ":"check","line":"373","key":"Certificate has CRL Distribution Points:","label":"yes","value":"yes"},
  {"typ":"check","line":"374","key":"Certificate has valid CRL URL:","label":"yes","value":"yes"},
  {"typ":"check","line":"375","key":"Certificate lazy Extended Validation (EV):","label":"no ( <<invalid charcters in ex
  {"typ":"check","line":"376","key":"Certificate has no invalid characters in extensions:","label":"no ( <<invalid charc
  {"typ":"check","line":"377","key":"Certificate does not contain CR, NL, NULL characters:","label":"yes","value":"yes"}
  {"typ":"check","line":"378","key":"Certificate does not contain non-printable characters:","label":"yes","value":"yes"
  {"typ":"check","line":"379","key":"Certificate has OCSP Responder URL:","label":"yes","value":"yes"},
  {"typ":"check","line":"380","key":"Certificate has valid OCSP URL:","label":"yes","value":"yes"},
  {"typ":"check","line":"381","key":"Certificate Fingerprint is not MD5:","label":"yes","value":"yes"},
  {"typ":"check","line":"382","key":"Certificate Private Key Signature SHA2:","label":"yes","value":"yes"},
  {"typ":"check","line":"383","key":"Certificate Private Key with Encryption:","label":"yes","value":"yes"},
  {"typ":"check","line":"384","key":"Certificate Private Key Encryption known:","label":"yes","value":"yes"},
  {"typ":"check","line":"385","key":"Certificate Public Key with Encryption:","label":"yes","value":"yes"},
  {"typ":"check","line":"386","key":"Certificate Public Key Encryption known:","label":"yes","value":"yes"},
  {"typ":"check","line":"387","key":"Certificate Public Key Modulus Exponent =65537:","label":"yes","value":"yes"},
  {"typ":"check","line":"388","key":"Certificate Public Key Modulus Exponent >65537:","label":"no (65537)","value":"no (
  {"typ":"check","line":"389","key":"Certificate Public Key Modulus >16385 bits:","label":"yes","value":"yes"},
  {"typ":"check","line":"390","key":"Certificate is not expired:","label":"yes","value":"yes"},
  {"typ":"check","line":"391","key":"Certificate is valid:","label":"yes","value":"yes"},
  {"typ":"check","line":"392","key":"Certificate is not root CA:","label":"yes","value":"yes"},
  {"typ":"check","line":"393","key":"Certificate is not self-signed:","label":"no (sh: 3: command not found)","value":"n
  {"typ":"check","line":"394","key":"Certificate Basic Constraints is false:","label":"yes","value":"yes"},
  {"typ":"check","line":"395","key":"Certificate chain validated:","label":"yes","value":"yes"},
  {"typ":"check","line":"396","key":"Certificate is valid according given hostname:","label":"no (faalserver.faalkaart.n
  {"typ":"check","line":"397","key":"Certificate does not contain wildcards:","label":"yes","value":"yes"},
  {"typ":"check","line":"398","key":"Certificate's wildcard does not match hostname:","label":"yes","value":"yes"},
  {"typ":"check","line":"399","key":"Certificate subjectAltNames compliant to RFC2818:","label":"no (Given hostname 'faa
  {"typ":"check","line":"400","key":"Certificate Names compliant to RFC6125:","label":"yes","value":"yes"},
  {"typ":"check","line":"401","key":"Certificate Serial Number size RFC5280:","label":"yes","value":"yes"},
  {"typ":"check","line":"402","key":"Target redirects HTTP to HTTPS:","label":"yes","value":"yes"},
  {"typ":"check","line":"403","key":"Target redirects with status code 301:","label":"yes","value":"yes"},
  {"typ":"check","line":"404","key":"Target redirects not with 30x status code:","label":"yes","value":"yes"},
  {"typ":"check","line":"405","key":"Target redirects HTTP without STS header:","label":"no (max-age=31536000; includeSu
  {"typ":"check","line":"406","key":"Target redirects HTTP to HTTPS same host:","label":"yes","value":"yes"},
  {"typ":"check","line":"407","key":"Target redirect matches given host:","label":"yes","value":"yes"},
  {"typ":"check","line":"408","key":"Target does not send STS in meta tag:","label":"yes","value":"yes"},
  {"typ":"check","line":"409","key":"Target sends STS header:","label":"yes","value":"yes"},
  {"typ":"check","line":"410","key":"Target sends STS and no Location header:","label":"yes","value":"yes"},
  {"typ":"check","line":"411","key":"Target sends STS and no Refresh header:","label":"yes","value":"yes"},
  {"typ":"check","line":"412","key":"Target sends STS header with proper max-age:","label":"no (31536000 = 365 days)","v
  {"typ":"check","line":"413","key":"Target sends STS header with includeSubdomain:","label":"yes","value":"yes"},
  {"typ":"check","line":"414","key":"STS max-age not reset:","label":"yes","value":"yes"},
  {"typ":"check","line":"415","key":"STS max-age less than one day:","label":"no (> 86400)","value":"no (> 86400)"},
  {"typ":"check","line":"416","key":"STS max-age less than one month:","label":"no (> 2592000)","value":"no (> 2592000)"
  {"typ":"check","line":"417","key":"STS max-age less than one year:","label":"no (> 31536000)","value":"no (> 31536000)
  {"typ":"check","line":"418","key":"STS max-age more than 18 weeks:","label":"yes","value":"yes"},
  {"typ":"check","line":"419","key":"STS max-age more than one year:","label":"no (< 99999999)","value":"no (< 99999999)
  {"typ":"check","line":"420","key":"STS max-age < certificate's validity:","label":"no (1531304486 + 31536000 > 1537556
  {"typ":"check","line":"421","key":"Target sends Public Key Pins header:","label":"no ( )","value":"no ( )"},
  {"typ":"check","line":"422","key":"Target supports Krb5:","label":"no ( )","value":"no ( )"},
  {"typ":"check","line":"423","key":"Target supports PSK:","label":"no ( )","value":"no ( )"},
  {"typ":"check","line":"424","key":"Target supports PSK Identity Hint:","label":"no ( )","value":"no ( )"},
  {"typ":"check","line":"425","key":"Target supports TLS Session Ticket:","label":"no ( )","value":"no ( )"},
  {"typ":"check","line":"426","key":"Target TLS Session Ticket Lifetime:","label":"no ( )","value":"no ( )"},
  {"typ":"check","line":"427","key":"Target TLS Session Ticket is random:","label":"yes","value":"yes"},
  {"typ":"check","line":"428","key":"Target supports ALPN:","label":"no ( )","value":"no ( )"},
  {"typ":"check","line":"429","key":"Target supports  NPN:","label":"no ( )","value":"no ( )"},
  {"typ":"check","line":"430","key":"Target supports Secure Renegotiation:","label":"yes","value":"yes"},
  {"typ":"hint","line":"431","key":"8","label":"431","value":"!!Hint: checks only if renegotiation is implemented server
  {"typ":"check","line":"432","key":"Target supports Resumption:","label":"yes","value":"yes"},
  {"typ":"check","line":"433","key":"Target supports SRP:","label":"no ( )","value":"no ( )"},
  {"typ":"info","line":"434","key":"Total number of check results 'yes':","label":"57","value":"57"},
  {"typ":"info","line":"435","key":"Total number of check results 'no':","label":"39","value":"39"},
  {"typ":"info","line":"436","key":"Total number of offered ciphers:","label":"1","value":"1"},
  {"typ":"info","line":"437","key":"Total number of checked ciphers:","label":"306","value":"306"},
  {"typ":"info","line":"438","key":"Certificate Chain Depth count:","label":"0","value":"0"},
  {"typ":"info","line":"439","key":"Certificate Subject Altname count:","label":"1","value":"1"},
  {"typ":"info","line":"440","key":"Certificate Wildcards count:","label":"0","value":"0"},
  {"typ":"info","line":"441","key":"Certificate CPS size:","label":"1428 bytes","value":"1428 bytes"},
  {"typ":"info","line":"442","key":"Certificate CRL size:","label":"2010 bytes","value":"2010 bytes"},
  {"typ":"info","line":"443","key":"Certificate CRL data size:","label":"0 bytes","value":"0 bytes"},
  {"typ":"info","line":"444","key":"Certificate OCSP size:","label":"34 bytes","value":"34 bytes"},
  {"typ":"info","line":"445","key":"Certificate OIDs size:","label":"0 bytes","value":"0 bytes"},
  {"typ":"info","line":"446","key":"Certificate Subject Altname size:","label":"24 bytes","value":"24 bytes"},
  {"typ":"info","line":"447","key":"Certificate Chain size:","label":"0 bytes","value":"0 bytes"},
  {"typ":"info","line":"448","key":"Certificate Issuer size:","label":"51 bytes","value":"51 bytes"},
  {"typ":"info","line":"449","key":"Certificate PEM (base64) size:","label":"2520 bytes","value":"2520 bytes"},
  {"typ":"info","line":"450","key":"Certificate PEM (binary) size:","label":"1849 bytes","value":"1849 bytes"},
  {"typ":"info","line":"451","key":"Certificate Public Key size:","label":"4096 bits","value":"4096 bits"},
  {"typ":"info","line":"452","key":"Certificate Signature Key size:","label":"2048 bits","value":"2048 bits"},
  {"typ":"info","line":"453","key":"Certificate Subject size:","label":"27 bytes","value":"27 bytes"},
  {"typ":"info","line":"454","key":"Certificate Serial Number size:","label":"18 bytes","value":"18 bytes"},
  {"typ":"stat","key":"error","value":"0"},
  {"typ":"stat","key":"warning","value":"15"},
  {"typ":"stat","key":"cipher","value":"301"},
  {"typ":"stat","key":"check","value":"96"},
  {"typ":"stat","key":"info","value":"358"},
  {"typ":"stat","key":"skip","value":""},
  {"key":"CVE-2016-2107","value":"true"},
  {"key":"CVE-2016-9244","value":"false"}
]
"""
