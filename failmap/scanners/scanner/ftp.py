"""
Scans for missing AUTH TLS / AUTH SSL options in FTP servers.

# Docs:
# https://docs.python.org/3/library/ftplib.html#ftplib.FTP_TLS.ssl_version
# https://chenlego.me/2017/07/26/how-to-verify-which-ssltls-protocols-are-supported-on-the-ftp-server/
# AUTH https://stackoverflow.com/questions/37256862/how-to-check-if-ftp-server-offers-tls-support-in-python
"""

import logging
from ftplib import FTP, FTP_TLS, error_perm, error_proto, error_reply, error_temp

from celery import Task, group
from django.utils import timezone

from failmap.celery import ParentFailed, app
from failmap.organizations.models import Url
from failmap.scanners.models import Endpoint
from failmap.scanners.scanmanager.endpoint_scan_manager import EndpointScanManager
from failmap.scanners.scanner.scanner import (allowed_to_scan, endpoint_filters,
                                              q_configurations_to_scan, url_filters)

log = logging.getLogger(__name__)

# how often a task should be retried when encountering an expectable exception
MAX_RETRIES = 3
RETRY_DELAY = 10

# after which time (seconds) a pending task should no longer be accepted by a worker
# can also be a datetime.
EXPIRES = 3600  # one hour is more then enough

# also does discovery(!)


@app.task(queue='storage')
def compose_task(
    organizations_filter: dict = dict(),
    urls_filter: dict = dict(),
    endpoints_filter: dict = dict(),
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

    Other
    [x] Export DNSSEC scans / Urlgenericscans and map settings...
    """

    if not allowed_to_scan("scanner_ftp"):
        return group()

    default_filter = {"protocol": "ftp"}
    endpoints_filter = {**endpoints_filter, **default_filter}
    endpoints = Endpoint.objects.all().filter(q_configurations_to_scan(level='endpoint'), **endpoints_filter)
    endpoints = endpoint_filters(endpoints, organizations_filter, urls_filter, endpoints_filter)

    if not endpoints:
        log.warning('Applied filters resulted in no endpoints, thus no ftp tasks!')
        return group()

    # only unique endpoints
    endpoints = list(set(endpoints))

    log.info('Creating ftp scan task for %s endpoints.', len(endpoints))

    # The number of top level urls is negligible, so randomization is not needed.

    task = group(
        scan.si(endpoint.url.url, endpoint.port) | store.s(endpoint) for endpoint in endpoints
    )

    return task


def compose_discover_task(organizations_filter: dict = dict(), urls_filter: dict = dict(),
                          endpoints_filter: dict = dict()) -> Task:
    # ports = [21, 990, 2811, 5402, 6622, 20, 2121, 212121]  # All types different default ports.
    ports = [21]
    urls = Url.objects.all().filter(q_configurations_to_scan(level='url'), not_resolvable=False, is_dead=False)
    urls = url_filters(urls, organizations_filter, urls_filter, endpoints_filter)

    log.info('Creating ftp discover task for %s urls.', len(urls))

    task = group(
        # first iterate through ports, so there is more time between different connection attempts. Which reduces load
        # for the tested server. Also, the first port has the most hits :)
        discover.si(url.url, port) | store_when_new_or_kill_if_gone.s(
            url, port, 'ftp', 4) for port in ports for url in urls
    )

    return task


def compose_verify_task(organizations_filter: dict = dict(), urls_filter: dict = dict(),
                        endpoints_filter: dict = dict()) -> Task:

    default_filter = {"protocol": "ftp"}
    endpoints_filter = {**endpoints_filter, **default_filter}
    endpoints = Endpoint.objects.all().filter(q_configurations_to_scan(level='endpoint'), **endpoints_filter)
    endpoints = endpoint_filters(endpoints, organizations_filter, urls_filter, endpoints_filter)

    task = group(
        # first iterate through ports, so there is more time between different connection attempts. Which reduces load
        # for the tested server. Also, the first port has the most hits :)
        discover.si(endpoint.url.url, endpoint.port) | store_when_new_or_kill_if_gone.s(
            endpoint.url, endpoint.port, 'ftp', 4) for endpoint in endpoints
    )

    return task


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

    if result['supports_tls'] is 'Unknown' and result['supports_ssl'] is 'Unknown':
        level = 'unknown'
        message = "An FTP connection could not be established properly. Not possible to verify encryption."

    log.debug('Storing result: %s, for url: %s.', level, endpoint)

    if result:
        EndpointScanManager.add_scan('ftp', endpoint, level, message, str(result))

    # return something informative
    return {'status': 'success', 'result': level}


@app.task(queue='scanners',
          bind=True,
          default_retry_delay=RETRY_DELAY,
          retry_kwargs={'max_retries': MAX_RETRIES},
          expires=EXPIRES)
def scan(self, address: str, port: int):
    """
    Uses the dnssec scanner of dotse, which works pretty well.

    :param url:

    Possible problems as seen on: https://github.com/stjernstedt/Interlan/blob/master/script/functions
    Timeout of 240 seconds. Nothing more (oh wow).

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
    ftp = FTP_TLS()

    try:
        ftp.connect(address, port, 3)
        log.debug('Connecting to %s ' % address)
    except OSError:
        # [Errno 64] Host is down
        # log.debug('Could not connect to %s' % ip)
        # you'll get a lot HOST IS DOWN messages.
        return results
    except EOFError:
        # ftp behaves unexpectedly, so there is FTP but we don't know anything about it.
        # we cannot draw any conclusion regarding it's safety?
        return results
    except (error_perm, error_proto, error_temp, error_reply):
        # ftplib.error_perm: 502 Command not implemented. We can't assess it further.
        return results
    except Exception:
        # Or whatever exception in really rare cases.
        return results

    results['status'] = 'connected'
    try:
        results['welcome'] = ftp.getwelcome()
    except Exception:
        # we don't really care about the welcome message, it's here for beautification only.
        pass

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
        feats = ftp.voidcmd('FEAT')
        results['features'] = feats

        results['supports_tls'] = "AUTH TLS" in feats
        results['supports_ssl'] = "AUTH SSL" in feats
        log.debug(results)
    except (error_reply, error_perm, error_temp, error_proto):
        # An error was received, such as a not-implemented.
        # ftplib.error_perm: 502 Command not implemented.
        results['status'] = str(error_reply)
        log.error(results)

        # We can try AUTH TLS and AUTH SSL to see if something is supported, even if we don't have a list of FEAT
        try:
            ftp.voidcmd("AUTH TLS")
            results['supports_tls'] = True
        except (error_reply, error_perm, error_temp, error_proto):
            # we already had an error
            # ftplib.error_perm: 500 'AUTH TLS': command not understood
            results['supports_tls'] = False
        except Exception:
            # really don't know what to do here...
            pass

        try:
            ftp.voidcmd("AUTH SSL")
            results['supports_ssl'] = True
        except (error_reply, error_perm, error_temp, error_proto):
            # we already had an error
            # ftplib.error_perm: 500 'AUTH TLS': command not understood
            results['supports_ssl'] = False
        except Exception:
            # really don't know what to do here...
            pass

    except Exception:
        # ConnectionResetError: [Errno 54] Connection reset by peer etc...
        pass

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

    # try to gracefully close the connection, if that's not accepted by the server we flip the table and leave.
    try:
        ftp.quit()
    except Exception:
        ftp.close()

    return results


# tries and discover FTP servers by A) trying to open an FTP connection to a standard port.
# it will do on all known urls, and try a range of well known FTP ports and alternative ports.
@app.task(queue='scanners')
def discover(url: str, port: int):
    # https://en.wikipedia.org/wiki/List_of_TCP_and_UDP_port_numbers

    connected = False
    ftp = FTP()
    try:
        ftp.connect(url, port, 3)
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
