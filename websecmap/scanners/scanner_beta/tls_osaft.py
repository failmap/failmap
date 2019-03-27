import json
import logging
import os
import platform
import subprocess
from random import shuffle

from celery import Task, group
from django.conf import settings

from websecmap.celery import PRIO_HIGH, PRIO_LOW, PRIO_NORMAL, app
from websecmap.organizations.models import Organization, Url
from websecmap.scanners.models import Endpoint
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.__init__ import allowed_to_scan, q_configurations_to_scan
from websecmap.scanners.timeout import timeout

log = logging.getLogger(__package__)

"""
This scanner currently uses:
- Linux commands
- O-Saft (docker)
- gawk
- GO (external scripts)
- cert-chain-resolver


Note: the goal for qualys is to add as many external (non humanly possible) resources as possible to have the
competitive edge. Therefore their scans will probably deviate for a few percent from "simpler" scans such as ours.
Qualys grading: https://community.qualys.com/docs/DOC-6321-ssl-labs-grading-2018
Older grading: https://github.com/ssllabs/research/wiki/SSL-Server-Rating-Guide


Uses O-SAFT and a number of external scripts to perform complete validation of TLS/SSL akin to SSL Labs.

On Juli 2018 this memory leak in docker prevented correct usage of O-Saft. It would eat all memory.
'especially if the remote end would not read'... which happens all the time.
https://github.com/moby/vpnkit/issues/371#issuecomment-390248401


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


@app.task(queue="storage")
def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
    **kwargs
) -> Task:

    if not allowed_to_scan("tls_osaft"):
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

    shuffle(urls)  # spread the load

    if endpoints_filter:
        raise NotImplementedError('This scanner needs to be refactored to scan per endpoint.')

    if not urls:
        log.warning('Applied filters resulted in no urls, thus no osaft tls scan tasks!')
        return group()

    log.info('Creating osaft scan task for %s urls for %s organizations.', len(urls), len(organizations))

    # todo: IPv6 is not well supported in O-Saft... will be updated in the future. Let's see what it does now.
    # todo: find the O-Saft command for IPv6 scans.
    endpoints = Endpoint.objects.all().filter(url__in=urls, protocol="https", ip_version=4, is_dead=False)

    # tasks are prioritized in increasing order. Reason is that the chain has to be completed instead of a series of
    # actions buffered. Consider 100 scans. We've seen that normally, first 100x the first task is run, then 100x
    # the second one and then the last one. The problem with this is that the second task is performed quickly in a
    # burst. Thus flooding the system with 100 tasks, while the first task is better rate limited.

    # having 20 tasks on a worker run on a single docker osaft, (which has about 11 pids constantly) is
    # a pretty steady setup. No memory leaks, no PID increases. Many scans finish and about 3 scans per minute are
    # performed, which is pretty sweet. It's 3x Qualys :)

    # You can clearly see the bursts in the scans table :)
    task = group(run_osaft_scan.si(endpoint.url.url, endpoint.port)  # LOW
                 | ammend_unsuported_issues.s(endpoint.url.url, endpoint.port)  # NORMAL
                 | determine_grade.s()  # HIGH
                 | store_grade.s(endpoint) for endpoint in endpoints)  # HIGH
    return task


def compare_results():
    """
    Gets the latest scan results from previously done qualys scans. So to make it easier to compare output and see if
    this scanner needs extra implementations (or that there are bugs in O-Saft).

    :return:
    """
    # given refactoring, the old approach didn't work anymore. Code saved for when the implemenation is updated.

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
    """

    raise NotImplementedError


def start_osaft_container():
    # wait 10 seconds, which is the boot time of the container, otherwise too many containers ar emade?
    # docker: Error response from daemon: Conflict. The container name "/practical_bassi" is already in use by container
    # so you can try and spawn the same container over and over, which is fine. Nothing happens.
    # todo: check if the container is already up. We don't care about a range of errors while the scanner is starting

    # every scan will now run this command, which is not really efficient.
    docker_ps = ["docker", "ps"]
    output = get_standard_out(docker_ps)

    if "osaft" not in output:
        start_docker = ["docker", "run", "-ti", "--rm", "-d", "--name", "osaft", "--entrypoint", "/bin/sh",
                        "owasp/o-saft"]
        get_standard_out(start_docker)


def get_standard_out(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (standardout, junk) = process.communicate()
    return standardout.decode('utf-8')


"""
Using this construction the container will run out of memory and CPU. A slow CPU means that scans don't finish in time
and the result is a clusterfuck. So we should only add scans when there is room to do so.

We can set a max number of PID's (simultaneous scans), and have the task retry until there is enough room in the
container.

todo: we also want to finish a chain, instead os doing step 1 first for all servers. Perhaps higher prio on the
rest of the process (which is more quick).

CONTAINER ID    NAME     CPU %      MEM USAGE / LIMIT     MEM %      NET I/O             BLOCK I/O           PIDS
ee377bec815d    osaft    162.55%    1.684GiB / 1.952GiB   86.27%     126MB / 78.6MB      4.93GB / 385MB      141

After the first series of tasks has been processed, all tasks are moved to the next phase. This means at a single moment
a large volume of other scans is performed which can completely drain or kill any resources available. It's therefore
very important that all the tasks in this scan are performed more or less sequentially.

So wait until it's finished, and don't start too many tasks. Otherwise your system WILL crash.
"""


# todo: **WARNING: 201: Can\'t get IP for host \'raad.zutphen.nl:443\'; host ignored :)
@app.task(queue="4and6")
def run_osaft_scan_shared_container(address, port):
    start_osaft_container()

    # See run_osaft_scan for parameter documentation
    # This variant of osaft scan starts a single container to limit the amount of memory usage. Memory usage was
    # 14 gigabyte when using 8 worker threads. We need to cut that down to 1 gb or something like that.
    # altname is not in the check report?
    log.info("Running osaft scan on %s:%s" % (address, port))

    # docker exec -ti osaft /O-Saft/o-saft.pl
    # a limited total means that certain ciphers are not checked and all kinds of vulnerabilities arise.
    #  '--trace-key'
    o_saft_command = ['docker', 'exec', '-ti', 'osaft', '/O-Saft/o-saft.pl', '--legacy=key',
                      '--ssl-error-max=10', '--ssl-error-total=30', '+check',
                                "%s:%s" % (address, port)]
    log.info("O-Saft command: %s" % " ".join(o_saft_command))
    process = subprocess.Popen(o_saft_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (standardout, junk) = process.communicate()
    # log.info("O-Saft output:")
    standardout = standardout.decode("utf-8")
    if "Cannot connect to the Docker daemon" in standardout:
        raise EnvironmentError(standardout)

    if "dates" not in standardout:
        raise EnvironmentError("O-Saft report is not complete. Is O-Saft running? Call: %s" % " ".join(o_saft_command))

    # log.info(standardout)
    return standardout


# todo: try a timeout on this command.
# This has a hard time limit. If in two minutes there is no reply, there probably is no TLS or something fishy going on.
# 90 seconds is ABSOLUTELY not enough... let's try 180.
# Such non-updated servers we can find automatically and inspect by hand.
# max_retries: we're scanning daily. If it fails, it fails. Too bad.
# If this happens... no follow up task? Or other task processed? What is it waiting for?
# once a time limit is received, it keeps on going with time limits and there is never a completed scan...
# even though it says max retries 1.
# hangs completely... control+c doesn't work... queue locked...
# Note that the timeout can work against itself. Even while the task is killed, the process is still running in the
# docker container waiting to be finished. It's better to hang then to process failed tasks.
@app.task(queue="4and6", max_retries=1, priority=PRIO_LOW)
def run_osaft_scan(address, port):
    return run_osaft_scan_shared_container(address, port)


"""
Say goodbye to your ram when using this function :)
25 containers at the same time? HMMMMMMMMMMMM... nope :)
5bf410dcbcf5        owasp/o-saft     "perl /O-Saft/o-saft…"   33 seconds ago      Up 21 seconds  elated_brahmagupta
fb30b8407438        owasp/o-saft     "perl /O-Saft/o-saft…"   37 seconds ago      Up 26 seconds  eloquent_benz
22285b06085d        owasp/o-saft     "perl /O-Saft/o-saft…"   7 hours ago         Up 7 hours     relaxed_edison
29e6efa6a5e4        owasp/o-saft     "perl /O-Saft/o-saft…"   9 hours ago         Up 9 hours     reverent_kowalevski
8d47b5d7c1f4        owasp/o-saft     "perl /O-Saft/o-saft…"   9 hours ago         Up 9 hours     awesome_payne
6d5b549a1674        owasp/o-saft     "perl /O-Saft/o-saft…"   9 hours ago         Up 9 hours     vibrant_shaw
b430b506e7d3        owasp/o-saft     "perl /O-Saft/o-saft…"   9 hours ago         Up 9 hours     priceless_wozniak
64bb55038b0f        owasp/o-saft     "perl /O-Saft/o-saft…"   10 hours ago        Up 10 hours    loving_benz
80a85e8df743        owasp/o-saft     "perl /O-Saft/o-saft…"   10 hours ago        Up 10 hours    cranky_mccarthy
989c9033f1c2        owasp/o-saft     "perl /O-Saft/o-saft…"   10 hours ago        Up 10 hours    youthful_sinoussi
2dcdf767a9cf        owasp/o-saft     "perl /O-Saft/o-saft…"   12 hours ago        Up 12 hours    blissful_turing
043c0402c987        owasp/o-saft     "perl /O-Saft/o-saft…"   15 hours ago        Up 15 hours    vibrant_lovelace
3dfbaea0b905        owasp/o-saft     "perl /O-Saft/o-saft…"   15 hours ago        Up 15 hours    adoring_hermann
5c648a60e691        owasp/o-saft     "perl /O-Saft/o-saft…"   15 hours ago        Up 15 hours    tender_nightingale
65f2af1c2061        owasp/o-saft     "perl /O-Saft/o-saft…"   15 hours ago        Up 15 hours    gracious_mirzakhani
5a5b60365496        owasp/o-saft     "perl /O-Saft/o-saft…"   15 hours ago        Up 15 hours    eloquent_heyrovsky
2309f92448e4        owasp/o-saft     "perl /O-Saft/o-saft…"   15 hours ago        Up 15 hours    kind_hamilton
dc1052fd4c65        owasp/o-saft     "perl /O-Saft/o-saft…"   15 hours ago        Up 15 hours    vigilant_villani
d7098ea0d1ff        owasp/o-saft     "perl /O-Saft/o-saft…"   15 hours ago        Up 15 hours    silly_lewin
d21abdb679ca        owasp/o-saft     "perl /O-Saft/o-saft…"   15 hours ago        Up 15 hours    tender_leakey
469e55cbba40        owasp/o-saft     "perl /O-Saft/o-saft…"   15 hours ago        Up 15 hours    practical_bassi
7da5f5236e43        owasp/o-saft     "perl /O-Saft/o-saft…"   15 hours ago        Up 15 hours    gracious_liskov
43c7c4575106        owasp/o-saft     "perl /O-Saft/o-saft…"   15 hours ago        Up 15 hours    flamboyant_visvesvaraya
3e94b4dca56c        owasp/o-saft     "perl /O-Saft/o-saft…"   15 hours ago        Up 15 hours    adoring_heisenberg
c867bf514f17        owasp/o-saft     "perl /O-Saft/o-saft…"   17 hours ago        Up 17 hours    boring_edison
"""


def run_osaft_scan_dedicated_container(address, port):
    # we're expecting SNI running everywhere. So we cant connect on IP alone, an equiv of http "host-header" is required
    # We're not storing anything on the filesystem and expect no dependencies on the O-Saft system. All post-processing
    # is done on another machine.

    # --trace-key: adds a key to follow the specific commands: the labels then can change without affecting this script
    # --legacy=quick : makes sure we're getting the json in proper output
    # +check performs an extensive array of checks
    # --ssl-error-max=5 prevents indefinite hangs on urls without TLS at all

    # owasp/o-saft --trace-key --legacy=quick +check https://faalkaart.nl
    # todo: determine call routine to O-Saft, docker is fine during development, but what during production?
    # todo: running O-Saft on a website without https (http://) makes O-Saft hang.
    log.info("Running osaft scan on %s:%s" % (address, port))
    # **WARNING: 048: additional commands in conjunction with '+check' are not supported; +'selfsigned' ignored
    o_saft_command = ['docker', 'run', '--rm', '-it',
                                'owasp/o-saft', '--trace-key', '--legacy=quick', '--ssl-error-max=5', '+check',
                                "%s:%s" % (address, port)]
    log.info("O-Saft command: %s" % o_saft_command)
    process = subprocess.Popen(o_saft_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (standardout, junk) = process.communicate()
    log.info("O-Saft output:")
    log.info(standardout)
    if "Cannot connect to the Docker daemon" in standardout:
        raise EnvironmentError(standardout)

    return standardout


# hooray for command injection from osaft output. If you can manipulate that, we're done :)
# you can do so at any point in for example the contents of the HSTS header. So this is a really insecure way of
# processing the output.
def gawk(string):
    # todo: check that gawk is installed
    # echo string | gawk -f contrib/JSON-array.awk
    echo = subprocess.Popen(["echo", string], stdout=subprocess.PIPE)
    gawk = subprocess.Popen(["gawk", "-f", osaft_JSON], stdin=echo.stdout, stdout=subprocess.PIPE)
    echo.stdout.close()  # Allow p1 to receive a SIGPIPE if p2 exits.
    output, err = gawk.communicate()

    # log.debug("gawk output:")
    # log.debug(output)
    return output.decode('utf-8')


@app.task(queue="4and6", priority=PRIO_NORMAL)
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
    lines = lines.splitlines()  # split the report in multiple lines, to inject findings
    lines = lines[:-1]  # make it possible to inject some other findings by removing the closing tag.

    log.debug('Running workaround scans to complete O-Saft')
    try:
        vulnerable = test_cve_2016_2107(address, port)
        string = '  {"typ": "check", "key": "[CVE-2016-2107]", "label": "Safe against CVE-2016-2107:", "value":"' + \
                 ("no (vulnerable)" if bool(vulnerable) else "yes") + '"},'
        lines.append(string)
    except TimeoutError:

        string = ' {"typ": "check", "key": "[CVE-2016-2107]", ' \
                 '"label": "Safe against CVE-2016-2107:", "value":"unknown"},'
        lines.append(string)

    try:
        vulnerable = test_cve_2016_9244(address, port)
        string = '  {"typ": "check", "key": "[CVE-2016-9244]", "label": "Safe against CVE-2016-9244:", "value":"' + \
                 ("no (vulnerable)" if bool(vulnerable) else "yes") + '"},'
        lines.append(string)
    except TimeoutError:
        string = ' {"typ": "check", "key": "[CVE-2016-9244]", ' \
                 '"label": "Safe against CVE-2016-9244:", "value":"unknown"},'
        lines.append(string)

    # Able to resolve the whole certificate chain
    string = '  {"typ": "check", "key": "[certchaincomplete]", "label": "Certificate chain can be resolved", ' \
             '"value":"' + ("yes" if cert_chain_is_complete(address, port) else "no (missing certs)") + '"},'
    lines.append(string)

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
        if line['key'] == '[' + key + ']':
            if line['value'].lower() != asserted_value:
                return {'trusted': False, 'message': message_if_assertion_failed,
                        'debug_key': line['key'], 'debug_value': line['value']}
            else:
                # empty values are not added to the list.
                # give back the correct value, for debugging purposes.
                return {'trusted': True, 'message': 'OK',
                        'debug_key': line['key'], 'debug_value': line['value']}

    raise KeyError("Key %s is not in report." % key)


def security_check(report, key, asserted_value, grade_if_assertion_failed, message_if_assertion_failed):
    for line in report:
        if line['key'] == '[' + key + ']':
            # Please note that O-Saft uses the severity written lowercase or uppercase.
            if line['value'].lower() != asserted_value:
                return {'grade': grade_if_assertion_failed, 'message': message_if_assertion_failed,
                        'debug_key': line['key'], 'debug_value': line['value']}
            else:
                # empty values are not added to the list.
                # give back the correct value, for debugging purposes.
                return {'grade': '', 'message': 'OK',
                        'debug_key': line['key'], 'debug_value': line['value']}

    raise KeyError("Key %s is not in report." % key)


# Done: added cipher to report in JSON-array.awk in O-Saft
def weak_cipher_check(report, grade_if_assertion_failed, message_if_assertion_failed):
    for line in report:
        if line['typ'] == 'cipher' and line['value'].lower() == "weak" and line['supported'] == "yes":
            return {'grade': grade_if_assertion_failed, 'message': message_if_assertion_failed,
                    'debug_key': line['key'], 'debug_value': line['value']}

    # not found
    # empty values are not added to the list.
    # give back the correct value, for debugging purposes.
    return {'grade': '', 'message': 'OK',
            'debug_key': 'no weak ciphers'}


def security_value(report, key):
    for line in report:
        if line['key'] == '[' + key + ']':
            return line['value'].lower()


# O-Saft has a compound output which sometimes places values in the wrong column.
def security_label(report, key):
    for line in report:
        if line['key'] == '[' + key + ']':
            return line['label'].lower()


@app.task(queue="storage", priority=PRIO_HIGH)
def determine_grade(report):
    """
    Use the docker build of OSaft, otherwise you'll be building SSL until you've met all dependencies.
    O-Saft very neatly performs a lot of checks that we don't have to do anymore ourselves, wrongly.

    :param report: json report from O-Saft with injections
    :return: two lists of grades.
    """
    # todo: A+ DNS Certification Authority Authorization (CAA) Policy found for this domain.

    if not report:
        return [], []

    # list of items wether the certificate can be trusted or not (has chain of trust etc)
    # if any of the is_trusted is False, then there is no trust, which affects the rating (instant F)
    is_trusted = []
    is_trusted.append(trust_check(report, "dates", "yes", "Certificate is not valid anymore."))

    # todo: https://github.com/OWASP/O-Saft/issues/107
    # should work after instructions...
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

    """
    https://sweet32.info/

    You can use the scanning tool form Qualys SSL Labs. In the "Handshake Simulation" section, you should see 3DES or
    RC4 only with browsers that don't support stronger ciphersuites, like IE6/XP and IE8/XP. If you have 3DES
    ciphersuites at the bottom of the "Cipher Suites" section, you can try to remove them, but it's not an
    immediate security issue. Removing 3DES will protect you against potential downgrade attack, but it will also break
    connections from older clients.

    Thus: if the server prefers other ciphers than the sweet32 ciphers, it's reasonably safe. Qualys says there are
    weak ciphers but doesn't highlight the Sweet32 vulnerability. This basically means that you will only get an F
    if you have a "sweet" cipher as a preferred cipher.

    We can find the used cipher using cipher_selected. The rest of the order is unclear for now.

    The cipher_selected is a convoluted value containing both the string representation of a cipher and the security
    cipher_selected = ECDHE-RSA-AES256-GCM-SHA384 HIGH
    We're splitting that into:
    """
    selected_cipher = security_label(report, "cipher_selected")
    log.debug("Connection has selected cipher: %s" % selected_cipher)

    if not selected_cipher:
        raise Exception("No selected_cipher detected, cannot perform checks.")

    # the selected cipher is a cipher where the Sweet 32 attack works.
    if selected_cipher in security_value(report, "sweet32"):
        ratings.append(security_check(report, "sweet32", "yes", "F", "Vulnerable to Sweet32."))

    """
    https://en.wikipedia.org/wiki/Lucky_Thirteen_attack

    Also focuses on CBC ciphers first. As such it is not listed in Qualys report. You see that both sweet32 and lucky13
    have the same ciphers that cause trouble in scans. The same logic is applied: this is only a problem if the client
    is weak / vulnerable.
    """
    if selected_cipher in security_value(report, "lucky13"):
        ratings.append(security_check(report, "lucky13", "yes", "F", "Vulnerable to Lucky 13."))

    # external tools may result in "unknown"
    if security_value(report, "CVE-2016-2107") not in ["yes", "unknown"]:
        ratings.append(security_check(report, "CVE-2016-2107", "yes", "F",
                                      "Vulnerable to CVE_2016_2107 (padding oracle)."))

    if security_value(report, "CVE-2016-9244") not in ["yes", "unknown"]:
        ratings.append(security_check(report, "CVE-2016-9244", "yes", "F",
                                      "Vulnerable to CVE_2016_9244 (ticketbleed)."))

    ratings.append(security_check(report, "hassslv2", "yes", "F", "Insecure/Obsolete protocol supported (SSLv2)."))
    ratings.append(security_check(report, "hassslv3", "yes", "F", "Insecure/Obsolete protocol supported (SSLv3)."))

    # todo: this is not always correct...
    ratings.append(security_check(report, "logjam", "yes", "F", "Vulnerable to Logjam."))

    # This is not an F in qualys. Sometimes they show weak ciphers, but don't trigger any ratings on it.
    # weak ciphers are supported everywhere.... We have to find out when.
    # Qualys will rate it an F if the cipher has been selected,
    # 2018 july: TLS1 and weak is not detrimental to a rating.
    # So only if the selected cipher is weak, this is a problem?
    # O-Saft output does not support visibility in what ciphers are used PER TLS version, which does not allow this
    # check. :(
    # ratings.append(weak_cipher_check(report, "F", "Insecure ciphers supported."))

    # Beast is not awarded any rating in Qualys anymore, as being purely client-side.
    # no BEAST check here.
    ratings.append(security_check(report, "crime", "yes", "F", "Vulnerable to CRIME attack, due to compression used."))
    # todo: robot ( and the new robot)
    ratings.append(security_check(report, "drown", "yes", "F", "Vulnerable to DROWN attack. If this certificate is "
                                                               "used elsewhere, they are also vulnerable."))

    # Todo: does O-Saft not check AECDH cipher usage? Or is that included.
    ratings.append(security_check(report, "cipher_adh", "yes", "F", "Anonymous (insecure) suites used."))

    # C-Class
    # This does not check for TLS 1.3, which will come. Or have to come.
    # not trustworthy...
    ratings.append(security_check(report, "hastls12", "yes", "C",
                                  "The server supports older protocols, but not TLSv1.2."))

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
    # This error pops up if the cipher check has been cancelled (or the amount of errors was higher than the threshold)
    # Should the threshold be applicable per protocol? It has to be increased now.
    # {'typ': 'warning', 'line': '19', 'key': '8', 'label': '19', 'value': '**WARNING: 301: TLSv12:
    # (1 of 193 ciphers checked) abort connection attempts after 10 total errors'} Total is too low.
    ratings.append(security_check(
        report, "rc4", "yes", "F", "RC4 is accepted and poses a weakness."))

    # Qualys checks for low bit ciphers in modern protocols. Specifically
    # ['3DES', 'RC4', 'IDEA', 'RC2'] in ['TLSv1.2', 'TLSv1.1', 'TLSv1.0'], if so:
    # ['C', 'Using old 64-bit block cipher(s) (3DES / DES / RC2 / IDEA) with modern protocols.']

    # B-Class
    ratings.append(security_check(
        report, "certchaincomplete", "yes", "B", "Certificate chain could not be resolved."))

    # Unknown Class
    # These are weaknesses described in O-Saft but not directly visible in Qualys. All ratings below might mis-match
    # the qualys rating. This can turn out to be a misalignment (where this or qualys is stronger).
    # Qualys doesn't care. Perhaps due to client selection.
    # ratings.append(security_check(
    #    report, "cipher_strong", "yes", "B", "Server does not prefer strongest encryption first."))

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


@app.task(queue="storage", priority=PRIO_HIGH)
def store_grade(combined_ratings, endpoint):
    ratings, trust_ratings, report = combined_ratings

    trusted = final_trust(trust_ratings)
    grade = final_grade(ratings)

    # This is how qualys normally migrates the normal rating when there is trust.
    if trusted != "T":
        trusted = grade

    store_endpoint_scan_result('tls_osaft_certificate_trusted', endpoint, trusted, "")
    store_endpoint_scan_result('tls_osaft_encryption_quality', endpoint, grade, "")


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
    :param url:
    :param port:
    :return:
    """

    openssl = settings.TOOLS['openssl']['executable'][platform.system()]

    # should complete near instantly (< 1 sec)
    # true | openssl s_client -connect google.com:443 2>/dev/null | openssl x509
    true_command = ['true']
    true = subprocess.Popen(true_command, stdout=subprocess.PIPE)
    openssl_command = [openssl, 's_client', '-connect', '%s:%s' % (url, port)]
    openssl = subprocess.Popen(openssl_command, stdin=true.stdout, stdout=subprocess.PIPE)
    openssl_output, err = openssl.communicate()
    # log.debug("openssl: %s" % openssl_output)

    # Why use an extra command just to extract begin/end?
    # x509_command = [openssl, 'x509']
    # x509 = subprocess.Popen(x509_command, stdin=openssl.stdout, stdout=subprocess.PIPE)
    # x509_output, err = x509.communicate()
    # log.debug("x509: %s" % x509_output)
    x509_output = find_including(openssl_output.decode('utf-8'),
                                 "-----BEGIN CERTIFICATE-----", "-----END CERTIFICATE-----")

    # cert chain resovler needs a file...
    output_dir = settings.TOOLS['TLS']['tls_check_output_dir']
    path = output_dir + "%s_%s.pem" % (url, port)
    with open(path, 'w') as the_file:
        the_file.write(x509_output)
    log.debug('File written to: %s' % the_file)

    # writes to stdout by default
    cert_chain_resolver = settings.TOOLS['TLS']['cert_chain_resolver'][platform.system()]
    certchain_command = [cert_chain_resolver, path]
    log.debug("Certchain command: %s" % " ".join(certchain_command))
    certchain = subprocess.Popen(certchain_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    certchain_output, err = certchain.communicate()
    certchain_output = certchain_output.decode('utf-8')
    log.debug("certchain: %s" % certchain_output)
    err = err.decode('utf-8')
    log.debug(err)

    # certchain_output contains the certificates downloaded to make the chain complete.
    # err contains the real output of the check.
    if "Invalid certificate" in err:
        return False

    if "Certificate chain complete." in err:
        return True

    return False


# abcdefghijkl: bc, jk = bcdefghijk
def find_including(s, first, last):
    try:
        start = s.index(first)
        end = s.rindex(last, start) + len(last)
        return s[start:end]
    except ValueError:
        return ""


# abcdefghijkl: abc, jkl = defghi
def find_between(s, first, last):
    try:
        start = s.rindex(first) + len(first)
        end = s.index(last, start)
        return s[start:end]
    except ValueError:
        return ""


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
