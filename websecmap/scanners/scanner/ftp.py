"""
Scans for missing AUTH TLS / AUTH SSL options in FTP servers.

# Docs:
# https://docs.python.org/3/library/ftplib.html#ftplib.FTP_TLS.ssl_version
# https://chenlego.me/2017/07/26/how-to-verify-which-ssltls-protocols-are-supported-on-the-ftp-server/
# AUTH https://stackoverflow.com/questions/37256862/how-to-check-if-ftp-server-offers-tls-support-in-python
"""

import logging
from ftplib import FTP, error_perm, error_proto, error_reply, error_temp

from celery import Task, group
from django.utils import timezone

from websecmap.celery import ParentFailed, app
from websecmap.organizations.models import Url
from websecmap.scanners.models import Endpoint
from websecmap.scanners.scanmanager import store_endpoint_scan_result
from websecmap.scanners.scanner.scanner import (allowed_to_scan, endpoint_filters,
                                                q_configurations_to_scan, url_filters)

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
    """
    Todo's:
    [X] Created allowed_to_scan permission in config.
    [X] Implemented scanner
    [X] Stored scan result
    [X] Processed scan result in report
    [X] Added risk filter on the map for this issue
    [X] Added graphs, stats and more
    [X] Created translations
    """

    if not allowed_to_scan("ftp"):
        return group()

    default_filter = {"protocol": "ftp", "is_dead": False}
    endpoints_filter = {**endpoints_filter, **default_filter}
    endpoints = Endpoint.objects.all().filter(q_configurations_to_scan(level='endpoint'), **endpoints_filter)
    endpoints = endpoint_filters(endpoints, organizations_filter, urls_filter, endpoints_filter)

    if not endpoints:
        log.warning('Applied filters resulted in no endpoints, thus no ftp tasks!')
        return group()

    for endpoint in endpoints:
        log.info("Going to scan: %s" % endpoint)

    endpoints = list(set(endpoints))

    log.info('Creating ftp scan task for %s endpoints.', len(endpoints))
    tasks = []

    for endpoint in endpoints:
        queue = "ipv4" if endpoint.ip_version == 4 else "ipv6"
        tasks.append(scan.si(endpoint.url.url, endpoint.port).set(queue=queue)
                     | store.s(endpoint))

    return group(tasks)


def compose_discover_task(organizations_filter: dict = dict(), urls_filter: dict = dict(),
                          endpoints_filter: dict = dict(), **kwargs) -> Task:
    # ports = [21, 990, 2811, 5402, 6622, 20, 2121, 212121]  # All types different default ports.

    log.debug("discovery")
    log.debug("o: %s, u: %s, e: %s" % (organizations_filter, urls_filter, endpoints_filter))

    ports = [21]
    urls = Url.objects.all().filter(q_configurations_to_scan(level='url'), not_resolvable=False, is_dead=False)

    # This can deliver 300+ urls if the url is shared over 300+ organizations
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter)

    # to reduce the amount of organizations returned... which doesn't work as the amount of urls can be enormous
    # which is not supported in an __in command.
    urls = list(set(urls))

    log.info('Creating ftp discover task for %s urls. %s' % (len(urls), urls))

    tasks = []
    for ip_version in [4, 6]:
        queue = "ipv4" if ip_version == 4 else "ipv6"
        # first iterate through ports, so there is more time between different connection attempts. Which reduces load
        # for the tested server. Also, the first port has the most hits :)
        for port in ports:
            for url in urls:
                tasks.append(discover.si(url.url, port).set(queue=queue)
                             | store_when_new_or_kill_if_gone.s(url, port, 'ftp', ip_version))

    return group(tasks)


def compose_verify_task(organizations_filter: dict = dict(), urls_filter: dict = dict(),
                        endpoints_filter: dict = dict(), **kwargs) -> Task:

    default_filter = {"protocol": "ftp", "is_dead": False}
    endpoints_filter = {**endpoints_filter, **default_filter}
    endpoints = Endpoint.objects.all().filter(q_configurations_to_scan(level='endpoint'), **endpoints_filter)
    endpoints = endpoint_filters(endpoints, organizations_filter, urls_filter, endpoints_filter)

    tasks = []

    for endpoint in endpoints:
        queue = "ipv4" if endpoint.ip_version == 4 else "ipv6"
        tasks.append(discover.si(endpoint.url.url, endpoint.port).set(queue=queue)
                     | store_when_new_or_kill_if_gone.s(endpoint.url, endpoint.port, 'ftp', endpoint.ip_version))

    return group(tasks)


@app.task(queue='storage')
def store(result: dict, endpoint: Endpoint):
    """

    :param result: param endpoint:
    :param endpoint:

    """
    level = ""
    message = ""

    # if scan task failed, ignore the result (exception) and report failed status
    if isinstance(result, Exception):
        return ParentFailed('skipping result parsing because scan failed.', cause=result)

    # analyze result
    if result['supports_ssl'] is True and result['supports_tls'] in [False, 'Unknown']:
        level = "outdated"
        message = "FTP Server only supports insecure SSL protocol."

    if result['supports_tls'] is True:
        level = "secure"
        message = "FTP Server supports TLS encryption protocol."

    if result['supports_tls'] in [False, 'Unknown'] and result['supports_ssl'] in [False, 'Unknown']:
        level = "insecure"
        message = "FTP Server does not support encrypted transport or has protocol issues."

    if result['supports_tls'] == 'Unknown' and result['supports_ssl'] == 'Unknown':
        level = 'unknown'
        message = "An FTP connection could not be established properly. Not possible to verify encryption."

    log.debug('Storing result: %s, for url: %s.', level, endpoint)

    if result:
        store_endpoint_scan_result('ftp', endpoint, level, message, str(result))

    # return something informative
    return {'status': 'success', 'result': level}


# supporting 4 and 6, whatever resolves to the FTP server is fine.
@app.task(bind=True,
          default_retry_delay=RETRY_DELAY,
          retry_kwargs={'max_retries': MAX_RETRIES},
          expires=EXPIRES,
          rate_limit="6/m")
def scan(self, address: str, port: int):
    """
    Uses the dnssec scanner of dotse, which works pretty well.

    :param url:

    Possible problems as seen on: https://github.com/stjernstedt/Interlan/blob/master/script/functions
    Timeout of 240 seconds. Nothing more (oh wow).


    # To determine what encryption protocols are supported, a login() is required.
    # Various options auto-negotiate to the highest possible security grade.
    # so meaning supporting SSLv2 is not often used. yet, as with webservers,
    # SSL2 is insecure and should be disabled completely.
    # Example protocols...
    #    'supports_PROTOCOL_SSLv2': False,
    #    'supports_PROTOCOL_SSLv3': False,
    #    'supports_PROTOCOL_TLSv1': False,
    #    'supports_PROTOCOL_TLSv1_1': False,
    #    'supports_PROTOCOL_TLSv1_2': False,
    #    'supports_PROTOCOL_TLSv1_3': False,

    """

    # supports_ssl is outdated and implies non-secure connections can be set up.
    results = {
        'address': address,
        'port': port,
        'supports_tls': 'Unknown',
        'supports_ssl': 'Unknown',
        'encryption_protocol': 'Unknown',
        'status': '',
        'welcome': '',
        'features': '',
    }

    # todo: this only connects to encrypted servers?
    ftp = FTP()

    try:
        ftp.connect(host=address, port=port, timeout=30)
        results['status'] += "Connected"
        log.debug('Connecting to %s ' % address)
    except OSError as Ex:
        log.debug("OSError: %s" % Ex)
        results['status'] += getattr(Ex, 'message', repr(Ex))
        # [Errno 64] Host is down
        # log.debug('Could not connect to %s' % ip)
        # you'll get a lot HOST IS DOWN messages.
        return results
    except EOFError as Ex:
        log.debug("EOFError: %s" % Ex)
        results['status'] += getattr(Ex, 'message', repr(Ex))
        # ftp behaves unexpectedly, so there is FTP but we don't know anything about it.
        # we cannot draw any conclusion regarding it's safety?
        return results
    except (error_perm, error_proto, error_temp, error_reply) as Ex:
        log.debug("FTP Error: %s" % Ex)
        results['status'] += getattr(Ex, 'message', repr(Ex))
        # ftplib.error_perm: 502 Command not implemented. We can't assess it further.
        return results
    except Exception as Ex:
        log.debug("Base Exception %s" % Ex)
        results['status'] += getattr(Ex, 'message', repr(Ex))
        # Or whatever exception in really rare cases.
        return results

    '''
    It's not allowed to perform "login" attempts, as that might look like an attack. We also don't want to test
    for logins, but we want to test for support of encryption.

    We can test for availability of encryption using the FEAT command. Most servers return a list of features
    such as the list below. From that list, we can determine if TLS/SSL is supported.

    Example output from FEAT:
    211- Extensions supported:
     AUTH TLS
     PBSZ
     PROT
     SIZE
     MDTM
     MFMT
     REST STREAM
     MLST type*;modify*;size*;UNIX.mode*;UNIX.owner*;UNIX.group*;
     MLSD
    '''

    try:
        results['features'] = ftp.voidcmd('FEAT')
        results['supports_tls'] = "AUTH TLS" in results['features']
        results['supports_ssl'] = "AUTH SSL" in results['features']
        # log.debug(results)
    except (error_reply, error_perm, error_temp, error_proto) as Ex:
        results['status'] += "FEAT Command: " + getattr(Ex, 'message', repr(Ex))
    except Exception as Ex:
        # and the other few million exception possibilities
        results['status'] += "FEAT Command: " + getattr(Ex, 'message', repr(Ex))

    # Even if the feat command delivered nothing, we're doing to AUTH anyway.
    if not results['supports_tls'] and not results['supports_ssl']:
        results['supports_tls'], result = try_tls(ftp)
        results['status'] += "Supports tls: %s" % result

        if not results['supports_tls']:
            # the fallback, even if it's not as secure.
            results['supports_ssl'], result = try_ssl(ftp)
            results['status'] += "Supports ssl: %s" % result

    # Don't get the welcome, it might give an exception and doesn't add that much
    # try:
    #     results['welcome'] = ftp.getwelcome()
    # except Exception:
    #     # we don't really care about the welcome message, it's here for beautification only.
    #     pass

    # try to gracefully close the connection, if that's not accepted by the server we flip the table and leave.
    try:
        ftp.quit()
        results['status'] += "Quit successfully"
    except Exception:
        ftp.close()
        results['status'] += "Force closed connection"

    return results


def try_ssl(ftp):
    try:
        ftp.voidcmd("AUTH SSL")
        return True, ""
    except (error_reply, error_perm, error_temp, error_proto) as Ex:
        log.debug(str(Ex))
        return False, getattr(Ex, 'message', repr(Ex))
    except Exception as Ex:
        log.debug(str(Ex))
        return False, getattr(Ex, 'message', repr(Ex))


def try_tls(ftp):
    try:
        ftp.voidcmd("AUTH TLS")
        return True, ""
    except (error_reply, error_perm, error_temp, error_proto) as Ex:
        log.debug(str(Ex))
        return False, getattr(Ex, 'message', repr(Ex))
    except Exception as Ex:
        log.debug(str(Ex))
        return False, getattr(Ex, 'message', repr(Ex))


# tries and discover FTP servers by A) trying to open an FTP connection to a standard port.
# it will do on all known urls, and try a range of well known FTP ports and alternative ports.
@app.task
def discover(url: str, port: int):
    # https://en.wikipedia.org/wiki/List_of_TCP_and_UDP_port_numbers

    connected = False
    ftp = FTP()
    try:
        ftp.connect(url, port, 30)
        connected = True
        ftp.close()
    except Exception:
        # we really don't care about an url that doesn't repond. 99% will not connect.
        pass

    # Pythons FTP library does not tell you about if it connected to IPv4 or IPv6.
    # We're going to (wrongly) assume it's always IPv4. This missing feature is a bummer.
    # Perhaps we could find out another way if this is an IPv4 or IPv6 address.
    return connected


@app.task(queue='storage')
def store_when_new_or_kill_if_gone(connected, url, port, protocol, ip_version):
    """

    :param url: any url where endpoints are discovered.
    :param port: any port: 1 to 65535
    :param protocol: any protocol in the endpoint table
    :param ip_version 4 or 6
    :param connected: True = Connected, False = Not Connected
    :return:
    """

    doesnotexist = False
    endpoint = None

    # get the latest info on this endpoint
    try:
        endpoint = Endpoint.objects.filter(protocol=protocol, port=port, ip_version=ip_version, url=url,
                                           is_dead=False).latest("discovered_on")
    except Endpoint.DoesNotExist:
        doesnotexist = True

    # Do not store updates to an endpoint that does not exist. We choose to NOT store endpoints that don't exist.
    # For the simple reason that otherwise 99% of our scans will result in an non existing endpoint, costing incredible
    # amounts of storage space.
    if doesnotexist and not connected:
        return

    # new endpoint! Store this endpoint as existing. Hooray, we found something new to scan.
    # We will not set old endpoints to alive.
    if doesnotexist and connected:
        ep = Endpoint(url=url, port=port, protocol=protocol, ip_version=ip_version, discovered_on=timezone.now())
        ep.save()
        return

    # endpoint was alive and still is. Nothing changed. We don't have a last seen date. So do nothing.
    if not endpoint.is_dead and connected:
        return

    # endpoint died. Kill it.
    if endpoint.is_dead is False and not connected:
        endpoint.is_dead = True
        endpoint.is_dead_reason = "Could not connect"
        endpoint.is_dead_since = timezone.now()
        endpoint.save()
        return
