"""
A worker gets a role from it's configuration. This role determines which queue's are processed by the worker.
The role also specifies what network connectivity is required (ipv4, ipv6 or both).

Note that hyper.sh workers only offer IPv4. (No sign of changing)
A normal Failmap server should have both IPv4 and IPv6 access.

On tricky issue:
The ROLE scanner requires both access to IPv4 and IPv6 networks.
The QUEUE scanner contains tasks that do not care about network family and can be either 4 or 6.
"""

import getpass
import logging
import os
import socket
import ssl
import tempfile

import certifi
import OpenSSL
from constance import config
from django.conf import settings
from kombu import Queue
from retry import retry

log = logging.getLogger(__name__)

TLS_CLIENT_FILE = '/client.p12'

# list of all roles that require internet connectivity
ROLES_REQUIRING_ANY_NETWORK = [
    'scanner',  # the queue scanner accepts 4and6, 4 or 6 - so ANY network scan :)
]

ROLES_REQUIRING_IPV4_AND_IPV6 = [
    'default',
]

# list of all roles that require IPv6 networking
ROLES_REQUIRING_IPV6 = [
    'scanner_v6',
    'scanner_ipv6_only',
]

ROLES_REQUIRING_IPV4 = [
    'scanner_v4',
    'scanner_ipv4_only',
    'scanner_qualys',  # only supports ipv4(!)
]

ROLES_REQUIRING_NO_NETWORK = [
    'storage',
]

# define roles for workers
QUEUES_MATCHING_ROLES = {
    # Select between roles.

    # universal worker that has access to database and internet on both v4 and v6
    'default': [
        # for tasks that require network connectivity to perform a scanning task, meaning any network connectivity
        # using both ipv4 and ipv6
        Queue('scanners'),
        # allow to differentiate on scan tasks that have specific ip network family requirements
        Queue('scanners.ipv4'),
        Queue('scanners.ipv6'),
        Queue('scanners.4and6'),  # both need to be present(!)
        # for tasks that require a database connection
        Queue('storage'),
        # default queue for task with no explicit queue assigned
        # these tasks should not expect network connectivity or database access!
        # Queue('default'), # deprecated
        # legacy default queue, can be removed after transition period to multiworkers
        # Queue('celery'),  # deprecated
        # endpoint discovery
        # just processing and calculations that require no database storage or network connectivity
        Queue('isolated'),  # tasks that require no network, no database.
    ],
    # universal worker without ipv6 specific queues
    'default_ipv4': [
        Queue('scanners'),  # tasks that requires ANY network
        Queue('scanners.ipv4'),  # or specific ipv4
        Queue('storage'),  # database access... why?
        Queue('isolated'),  # tasks that require no network, no database.
        # Queue('default'),  # no explicit queue means uncertainty about network requirements.
        # Queue('celery'),  # see default
    ],
    'scanner_v4': [
        Queue('scanners'),  # tasks that requires ANY network
        Queue('scanners.ipv4'),  # specifically ipv4
        Queue('isolated'),  # tasks that require no network, no database.
    ],
    'scanner_v6': [
        Queue('scanners'),  # requires ANY network
        Queue('scanners.ipv6'),
        Queue('isolated'),
    ],
    # worker with access to storage allowed to connect to databases
    'storage': [
        Queue('storage'),
        Queue('isolated'),  # to test the dummy scanner, you don't have any access to the network.
    ],
    # universal scanner worker that has internet access for both IPv4 and IPv6
    'scanner': [
        Queue('scanners'),  # tasks that requires ANY network
        Queue('isolated'),  # no network, no database
    ],
    # special scanner worker for qualys rate limited tasks to not block queue for other tasks
    # and it needs a dedicated IP address, which is coded in hyper workers.
    'scanner_qualys': [
        Queue('scanners.qualys'),
    ],
    # scanner with no IPv6 connectivity
    # this is an initial concept and can later be replaced with universal
    # scanner that automatically detects connectivity
    'scanner_ipv4_only': [
        Queue('scanners.ipv4'),
    ],
    'scanner_ipv6_only': [
        Queue('scanners.ipv6'),
    ],
}


def worker_configuration():
    """Apply specific configuration for worker depending on environment."""

    role = os.environ.get('WORKER_ROLE', 'default')

    log.info('Configuring worker for role: %s', role)

    # configure which queues should be consumed depending on assigned role for this worker
    return {'task_queues': QUEUES_MATCHING_ROLES[role]}


@retry(tries=3, delay=5)
def worker_verify_role_capabilities(role):
    """Determine if chosen role can be performed on this host (eg: ipv6 connectivity.)"""

    failed = False

    if role in ROLES_REQUIRING_NO_NETWORK:
        return not failed

    if role in ROLES_REQUIRING_IPV6 or role in ROLES_REQUIRING_IPV4_AND_IPV6:
        # verify if a https connection to a IPv6 website can be made
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM, 0)
        try:
            s.connect((config.IPV6_TEST_DOMAIN, 443))
        except socket.gaierror:
            # docker container DNS might not be ready, retry
            raise
        except BaseException:
            log.warning('Failed to connect to ipv6 test domain %s via IPv6', config.IPV6_TEST_DOMAIN, exc_info=True)
            failed = True

    if role in ROLES_REQUIRING_IPV4 or role in ROLES_REQUIRING_IPV4_AND_IPV6:
        # verify if a https connection to a website can be made
        # we assume non-ipv4 internet doesn't exist
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        try:
            s.connect((config.CONNECTIVITY_TEST_DOMAIN, 443))
        except socket.gaierror:
            # docker container DNS might not be ready, retry
            raise
        except BaseException:
            log.warning('Failed to connect to test domain %s via IPv4', config.CONNECTIVITY_TEST_DOMAIN, exc_info=True)
            failed = True

    if role in ROLES_REQUIRING_ANY_NETWORK:
        # one may fail.

        # try v4 first
        s4 = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        try:
            s4.connect((config.IPV6_TEST_DOMAIN, 443))
        except socket.gaierror:
            # docker container DNS might not be ready, retry
            raise
        except BaseException:
            s6 = socket.socket(socket.AF_INET6, socket.SOCK_STREAM, 0)
            try:
                s6.connect((config.IPV6_TEST_DOMAIN, 443))
            except socket.gaierror:
                # docker container DNS might not be ready, retry
                raise
            except BaseException:
                log.warning('Failed to connect to test domain %s via both v6 and v6', config.CONNECTIVITY_TEST_DOMAIN,
                            exc_info=True)
                failed = True

    return not failed


def tls_client_certificate():
    """Configure certificates from PKCS12 file.

    If client file is provided will extract key and certificate pem to files and
    configure these with Celery. """

    tls_client_file = os.path.abspath(os.path.expanduser(
        os.environ.get('TLS_CLIENT_FILE', TLS_CLIENT_FILE)))

    if os.path.exists(tls_client_file):
        log.info('PKCS12 file found, configuring TLS for worker.')

        # try to open PKCS12 file without passphrase, if it fails ask for passphrase and try again
        try:
            p12 = OpenSSL.crypto.load_pkcs12(open(tls_client_file, 'rb').read())
        except OpenSSL.crypto.Error:
            log.warning('Failed to decrypt without passphrase.')

            passphrase = os.environ.get('PASSPHRASE')
            if passphrase:
                log.info('Got passphrase from environment')
            else:
                passphrase = getpass.getpass('Please provide passphrase for %s: ' % tls_client_file)
            p12 = OpenSSL.crypto.load_pkcs12(open(tls_client_file, 'rb').read(), passphrase)

        # store extracted key and cert in temporary files that are deleted on exit of the worker
        tls_client_cert_file = tempfile.NamedTemporaryFile(dir=settings.WORKER_TMPDIR, delete=False)
        tls_client_key_file = tempfile.NamedTemporaryFile(dir=settings.WORKER_TMPDIR, delete=False)
        tls_client_key_file.write(OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM, p12.get_privatekey()))
        tls_client_cert_file.write(OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, p12.get_certificate()))

        # configure redis to use TLS
        ssl_options = {
            'ssl_keyfile': tls_client_key_file.name,
            'ssl_certfile': tls_client_cert_file.name,
            'ssl_ca_certs': certifi.where(),
            'ssl_cert_reqs': ssl.CERT_REQUIRED,
        }
        return {
            'broker_use_ssl': ssl_options,
            'redis_backend_use_ssl': ssl_options,
        }
    else:
        log.info('no PKCS12 file found, not configuring TLS.')
        return {}
