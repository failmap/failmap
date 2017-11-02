import logging
import platform
import re
import subprocess
from datetime import datetime

import pytz
import untangle
from django.conf import settings

from celery_test import app
from failmap_admin.scanners.models import Endpoint
from failmap_admin.scanners.timeout import timeout

logger = logging.getLogger(__package__)

# uses sslscan to determine the quality of a tls connection. It's way faster than others and for
# the basis it results the same sanity checks. What sslscan misses is a "general" rating. This will
# be provided here.

# Next to sslscan there is also a python native solution, which is not compiled against an old ssl.
# sslize can do much of the same. It doesn't deliver on it's promise of discovering weak ciphers as
# advertised. Which is a shame.

# This might help to translate the names to standardized names. Complete?
# https://github.com/nabla-c0d3/sslyze/blob/d672fa4d039aa8468e466a3262b304228adde3d4/sslyze/
# plugins/openssl_cipher_suites_plugin.py

"""
Research:

sslyze: doesn't give any conclusions. It does not show if a certificate has expired.
sslscan: compiles against an tls library that is able to test ssl2 and such. That is much better.
sslscan is easier to install via a package manager (does that do all scans?)

This scanner will scan TLS on all ports and will find many of the most common weaknesses.
It's also able to check starttls on ftp, imap, irc, ldap, pop3, smtp, mysql, xmpp, postgres.


Specifications for grading:

Detail:                                    Grade:          In SslScan:                   Implemented
SSLv2                                      F (set)         Yes (as SSlv2 support)                  Y
SSLv3                                      B (set)         Yes (as SSlv3 support)                  Y
Not using the latest TLS v1.2              C (cap)         Yes (in cypher suites)                  Y
Poodle (SSL3)                              C (cap)         Yes (CBC in cipher)                     Y
Poodle SSL3 = C                                                                                    Y
Poodle TLS = F                                                                                     Y
Crime attack (no compression + more)       C (cap)         Yes                                     Y
Heartbleed tls 0, 1, 2                     F (set)         Yes                                     Y
Insecure Session renegotation /MITM        F (set)         Yes                                     Y

No Trust due to Expiration                 T (set)         Yes, in Certificate                     Y
No Trust due to Self Signed                T (set)         Yes, in Certificate                     Y
Certificate name mismatch                  T (set)         Yes, in Certificate                     Y

Insecure Diffie Helman exchange (logjam)   F (set)         Yes, in supported cyphers               Y
Weak Diffie Helman                         B (cap)         Yes                                     Y

RC4 Cipher, but only older protocols       B (cap)         Yes                                     Y
RC4 Cipher, with modern protocols 1.2, 1.1 C (cap)         Yes                                     Y

Anonymous Ciphers                          F               Yes (ADH, AECDH)                        Y

Insecure Cipher Suites                     F (set)         Yes, weak bits                          Y
                                                           Partial, some known weak ciphers        P

512 bit export suites (Freak attack)       F               Yes, in cipher suites, EXP              Y

OpenSSl Padding Oracle                     F (set)         No, use FiloScottile tool requires GO(!)Y
Ticketbleed                                Y               No, use other script. (see vendor dir)  Y

64-bit block cipher (3DES / DES / RC2 / IDEA)
with modern protocols                      C (cap)         Yes, in cipher suites                   P


Certificate Chain Incomplete               B (cap)         Not determined, No. Gets only only 1.
                                                           Use cert chain resolver.
To check: https://github.com/zakjan/cert-chain-resolver/


Revoked                                    F               No, requires revocation list.
Distrust in modern browsers (aka using revoked certificates) - This is a warning.
                                           T               Issue name against revocation list.
                                                           Spec StartCom + WoCom

Drown (similar key, using ssl2 elsehwere)  F               No, requires key database + updating.
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
Lucky 13: Todo.

What we should have used: https://www.owasp.org/index.php/O-Saft ... nah

"""


sslscan = settings.TOOLS['sslscan']['executable'][platform.system()]
output = settings.TOOLS['sslscan']['report_output_dir']

anonymous_ciphers = ['ADH-AES256-SHA', 'ADH-AES128-SHA', 'ADH-RC4-MD5', 'ADH-DES-CBC3-SHA',
                     'ADH-DES-CBC-SHA', 'EXP-ADH-DES-CBC-SHA', 'EXP-ADH-RC4-MD5', ]

anon_ciphers = ['0xc016', '0xc017', '0xc018', '0xc019']
weak_ciphers = ['0xa', '0x7', '0xa', '0xc012', '0x16', '0xc012']  # low bits.
insecure_ciphers = ['0x4', '0x5', '0xc011', '0x9', '0x15', '0x64', '0x10080', '0x30080', '0x700c0',
                    '0x60040', '0x20080', '0x40080']


# todo: options, host zetten. Anders SSLScan, dat valt op.

def scan_url(url):
    endpoints = Endpoint.objects.all().filter(url=url, protocol='https')
    for endpoint in endpoints:
        report = scan_endpoint(endpoint)
        rating, trust_rating = determine_grade(report, endpoint.url.url)
        store_grade(rating, trust_rating, endpoint)


def scan_real_url(url, port=443):
    """
    A scan takes about a minute to complete and can be run against any TLS website and many other
    services.
    :param url: string, internet address, not an url object(!)
    :param port: integer, port number.
    :return:
    """
    url_and_port = "%s:%s" % (url, port)
    now = str(datetime.now(pytz.utc).strftime("_%Y%m%d_%H%M%S_%f"))
    filename = str(re.sub(r'[^a-zA-Z0-9_]', '', url_and_port + now)) + '.xml'
    out = output + filename
    subprocess.call([sslscan, '--show-certificate', '--xml=' + out, url_and_port])

    # add some things to the XML file about external tools.
    # hacky hacky code :)
    file = open(out, 'r')
    lines = file.readlines()
    lines = lines[:-2]
    try:
        vulnerable = test_cve_2016_2107(url, port)
        string = "  <CVE-2016-2107>" + str(bool(vulnerable)) + "</CVE-2016-2107>"
        lines.append(string)
    except TimeoutError:
        pass

    try:
        vulnerable = test_cve_2016_9244(url, port)
        string = "  <CVE-2016-9244>" + str(bool(vulnerable)) + "</CVE-2016-9244>"
        lines.append(string)
    except TimeoutError:
        pass

    lines.append(" </ssltest>")
    lines.append("</document>")

    file.close()

    # overwrite it with the new "xml".
    with open(out, 'w') as f:
        f.write(''.join(lines))

    return out


@app.task
def scan_endpoint(endpoint, IPv6=False):
    return scan_real_url(endpoint.url.url, endpoint.port)


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


def testcase(filename, domain='example.com'):
    logger.info(filename)
    rating, trust_rating = determine_grade(output + 'testcases/' + filename + '.xml', domain)
    debug_grade(rating, trust_rating)


def test_real(url='faalkaart.nl', port=443):
    report = scan_real_url(url, port)
    rating, trust_rating = determine_grade(report, url)
    debug_grade(rating, trust_rating)


@app.task
def determine_grade(report, url):
    """
    Compared to other services, it's not needed to give a comprehensive report of all things that
    are wrong with the certificate / installation of the certificate.

    If we would, we _CAN_ give a comprehensive report of all the things we can check...
    Which results in a nicer presentation on the website.

    Just return the rating and an explanation asap.

    Please add your improvements into this function. Amazing that such an explanation is not in
    sslscan (if we could write C, we would).
    :param report:
    :return:
    """
    ratings = []
    trust_rating = []

    if not url:
        logger.error('No url given: %s' % url)
        return

    if not report:
        logger.error('No report given: %s' % report)
        return

    try:
        logger.debug('untangle.parse("%s")' % report)
        obj = untangle.parse(report)
    except Exception:
        logger.error('Something wrong with report file: %s' % report)
        return

    # Used the --show-certificate option
    # you want to have the last one.
    # are chains missing if there is less than 2?
    if obj.document.ssltest.certificate[1]:
        certificate = obj.document.ssltest.certificate[len(obj.document.ssltest.certificate) - 1]
    else:
        # ratings.append(['B', "Chain of trust missing."]) -> you never see the full list.
        certificate = obj.document.ssltest.certificate

    if hasattr(certificate, "self_signed") and certificate.self_signed.cdata == 'true':
        trust_rating.append(['False', "Certificate is self signed."])

    if certificate.expired.cdata == 'true':
        trust_rating.append(['False', "Certificate expired."])

    if 'sha1' in certificate.signature_algorithm.cdata:
        trust_rating.append(['False', "SHA1 signature Algorithm is obsolete."])

    # check if there is a mismatch, including all wildcard options
    testurls = []
    testurls.append(url)
    myurl = url
    while myurl.count('.') > 1:
        h, s, t, = myurl.partition('.')
        myurl = t
        testurls.append('*.' + t)

    altnames = certificate.altnames.cdata if hasattr(certificate, "altnames") else ""
    name_or_wildcard_found = False

    for testurl in testurls:
        # can be a wildcard certificate with one of the valid urls in altnames.
        if url == certificate.subject.cdata or ':' + testurl in altnames:
            name_or_wildcard_found = True

    if not name_or_wildcard_found:
        trust_rating.append(['False', "Certificate name mismatch."])

    # Heartbleed
    for heartbleed in obj.document.ssltest.heartbleed:
        if heartbleed['vulnerable'] == '1':
            ratings.append(['F', "Vulnerable to heartbleed on %s." % heartbleed['sslversion']])

    # Insecure renegotiation
    if obj.document.ssltest.renegotiation['supported'] == '1' and \
            obj.document.ssltest.renegotiation['secure'] == '0':
        ratings.append(['F', "Server does not support secure session renegotiation, "
                             "a Man In The Middle attack is possible."])

    # check for sslv2.
    for cipher in obj.document.ssltest.cipher:
        if cipher['sslversion'] == 'SSLv2':
            ratings.append(['F', "Insecure/Obsolete protocol supported (SSLv2)."])
            break

    # check for sslv3, poodle (this doesn't work that way)
    for cipher in obj.document.ssltest.cipher:
        if cipher['sslversion'] == 'SSLv3':
            ratings.append(['B', "Insecure/Obsolete protocol supported (SSLv3)."])
            break

    # poodle = sslv3 and not using 0x5 cipher.

    # Check for Missing TLSv1.2
    # todo: rewrite to more readable code without flag
    supports_tlsv12 = False
    for cipher in reversed(obj.document.ssltest.cipher):
        if cipher['sslversion'] == 'TLSv1.2':
            supports_tlsv12 = True
            break

    if not supports_tlsv12:
        ratings.append(['C', "Only older protocols are supported, but not the safest: TLSv1.2."])

    # Check for CRIME / TLS compression (BREACH?)
    # https://en.wikipedia.org/wiki/CRIME
    # todo: rating still unclear for compression enabled
    if obj.document.ssltest.compression['supported'] == '1':
        ratings.append(['C', "Vulnerable to CRIME attack, due to compression used."])

    # cipher checks
    ciphers = obj.document.ssltest.cipher

    # logjam (weak DH parameters), https://weakdh.org/ Everythiung under 1024 -preferably under 2048
    for cipher in ciphers:
        if cipher['dhebits'] and int(cipher['dhebits']) < 1024:
            ratings.append(['F', "Insecure Diffie-Hellman parameters used."])
            break

    # Weak diffie helman, now seen as 1024, might be > 768 < 2048?
    for cipher in ciphers:
        if cipher['dhebits'] and int(cipher['dhebits']) == 1024:
            ratings.append(['B', "Weak Diffie-Hellman parameters used."])
            break

    # RC4 for newer protocols (1.1, 1.2)
    for cipher in ciphers:
        if "RC4" in cipher['cipher'] and cipher['sslversion'] in ['TLSv1.2', 'TLSv1.1']:
            ratings.append(['C', "RC4 cipher accepted in modern protocols."])
            break

    # RC4 for older protocls (2, 3, 1.0)
    for cipher in ciphers:
        if "RC4" in cipher['cipher'] and cipher['sslversion'] in ['TLSv1.0', 'SSLv3', 'SSLv2']:
            ratings.append(['B', "RC4 cipher accepted in older protocols."])
            break

    # https://github.com/rbsec/sslscan/blob/master/sslscan.c
    # Null ciphers (insecure)
    for cipher in ciphers:
        if "NULL" == cipher['cipher']:
            ratings.append(['F', "NULL Cipher supported."])
            break

    # AnonymousDH or AnonymousECDH
    for cipher in ciphers:
        if "ADH" in cipher['cipher'] or "AECDH" in cipher['cipher']:
            ratings.append(['F', "Anonymous (insecure) suites used."])
            break

    # insecure ciphers (low bits)
    for cipher in ciphers:
        if cipher['bits'] and int(cipher['bits']) < 56:
            ratings.append(['F', "Insecure ciphers used (low number of bits)."])
            break

    # FREAK attack (RSA EXPORT) ciphers. The default sslscan will not find ALL these ciphers(!)
    # Multiple times the EXPORT ciphers are not visible in SSL3, and TLS. Only in SSLv2 and only
    # a few versus a complete set.
    for cipher in ciphers:
        if "EXP" in cipher['cipher'] or "EXPORT" in cipher['cipher']:
            ratings.append(['F', "RSA Export ciphers present, might be vulnerable to FREAK."])
            break

    # weak ciphers (low bits)
    # Even with weak ciphers, there is some security...(?)
    # for cipher in obj.document.ssltest.cipher:
    #     if cipher['bits'] and 56 <= int(cipher['bits']) <= 112:
    #         ratings.append(['C', "Weak ciphers used."])
    #         break

    # other insecure ciphers.
    for cipher in ciphers:
        if cipher['id'] in insecure_ciphers:
            ratings.append(['F', "Insecure ciphers used (known weak id)."])
            break

    # check for old 64 bit stuff:
    low_bit_things = ['3DES', 'RC4', 'IDEA', 'RC2']
    for cipher in ciphers:
        if cipher['sslversion'] in ['TLSv1.2', 'TLSv1.1', 'TLSv1.0']:
            for low_bit_thing in low_bit_things:
                if low_bit_thing in cipher['cipher']:
                    ratings.append(
                        ['C', 'Using old 64-bit block cipher(s) (3DES / DES / RC2 / IDEA) '
                              'with modern protocols.'])
                    break

    # Check for padding oracle vulnerability
    # <CVE-2016-2107>False</CVE-2016-2107>
    if hasattr(obj.document.ssltest, "CVE_2016_2107"):
        if obj.document.ssltest.CVE_2016_2107.cdata == 'True':
            ratings.append(['F', 'Vulnerable to CVE_2016-2107 (padding oracle).'])

    # Check for ticketbleed vulnerability
    # <CVE-2016_9244>False</CVE-2016_9244>
    if hasattr(obj.document.ssltest, "CVE_2016_9244"):
        if obj.document.ssltest.CVE_2016_9244.cdata == 'True':
            ratings.append(['F', 'Vulnerable to CVE_2016_9244 (ticketbleed).'])

    # Check for POODLE (CVE-2014-3566)
    # SSLv3 + CBC ciphersuites
    # https://nmap.org/nsedoc/scripts/ssl-poodle.html
    # this is incorrect? Or has this to do with the discovered software / server?
    # windows is not vulnerable?
    for cipher in ciphers:
        if cipher['sslversion'] in ['SSLv3'] and "CBC" in cipher['cipher']:
            ratings.append(
                ['C', 'Vulnerable to CVE_2014_3566 (POOODLE) on SSLv3. Remove CBC ciphers.'])
            break

    # Poodle on TLS v1 (this is incorrect...) todo: other scan. Can have CBC, but specific thing?
    for cipher in ciphers:
        if cipher['sslversion'] in ['TLSv1.0'] and "CBC" in cipher['cipher']:
            ratings.append(
                ['F', 'Vulnerable to CVE_2014_3566 (POOODLE) on TLS. Remove CBC ciphers.'])
            break
    # the preferred cipher is relevant. If preferred cipher is weak... i mean...

    # we don't check for HSTS, HPKP, that is done in the headers scanner. So this will not give
    # an a+. But just an A. - We can check in the header database if they use HPKP + HSTS.
    # however, we don't check on hpkp.

    if not ratings:
        ratings.append(['A', "Looks good!"])
    # DES

    return ratings, trust_rating


def debug_grade(ratings, trust_ratings):
    lowest_rating = 'A'
    trust = True
    logger.debug('-------------------------------------------------------------------')
    logger.debug('Trust')
    for rating in trust_ratings:
        logger.debug("  %s: %s" % (rating[0], rating[1]))
        trust = False
    logger.debug('')
    logger.debug('Trust:  %s' % trust)
    logger.debug('')

    logger.debug('Vulnerabilities')
    for rating in ratings:
        logger.debug("  %s: %s" % (rating[0], rating[1]))
        if rating[0] > lowest_rating:
            lowest_rating = rating[0]
    logger.debug('')
    logger.debug('Rating: %s' % lowest_rating)
    logger.debug('')


@app.task
def store_grade(ratings, trust_ratings, endpoint):
    lowest_rating = 'A'
    trust = True

    logger.debug('Trust')
    for rating in trust_ratings:
        logger.debug("%s: %s" % (rating[0], rating[1]))
        trust = False

    logger.debug('Vulnerabilities')
    for rating in ratings:
        logger.debug("%s: %s" % (rating[0], rating[1]))
        if rating[0] > lowest_rating:
            lowest_rating = rating[0]

    logger.debug('Conlcusion: rated %s with trust?: %s', (lowest_rating, trust))

    # EndpointScanManager.add_scan('ssl_tls', endpoint, grade, explanation)


@timeout(3)
def test_cve_2016_2107(url, port):
    # The script will timeout sometimes.
    # run GO package. go run main.go tweakers.net
    # get the first line output.

    # writes to stderror by default.
    process = subprocess.Popen(['go',
                                'run',
                                settings.TOOLS['TLS']['cve_2016_2107'],
                                "%s:%s" % (url, port)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # get last word of first line. Can be true or false. Should only get one line.
    out, err = process.communicate()
    print(out)
    print(err)
    if "Vulnerable: true" in str(err) or "Vulnerable: true" in str(out):
        return True
    return False


@timeout(3)
def test_cve_2016_9244(url, port):
    # The script will timeout sometimes.
    # run GO package. go run main.go tweakers.net
    # get the first line output.
    process = subprocess.Popen(['go',
                                'run',
                                settings.TOOLS['TLS']['cve_2016_9244'],
                                "%s:%s" % (url, port)],
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

    raise NotImplemented
