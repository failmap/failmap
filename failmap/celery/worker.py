import getpass
import logging
import os
import socket
import ssl
import tempfile

import certifi
import OpenSSL
from django.conf import settings
from kombu import Queue

log = logging.getLogger(__name__)

TLS_CLIENT_FILE = '/client.p12'
IPV6_TEST_DOMAIN = 'faalkaart.nl'
CONNECTIVITY_TEST_DOMAIN = 'faalkaart.nl'

# list of all roles that require IPv6 networking
IPV6_ROLES = [
    'default',
    'scanner_endpoint_discovery',
    'scanner_v6',
    'scanner',
]

# list of all roles that require internet connectivity
CONNECTIVITY_ROLES = [
    'default',
    'default_ipv4',
    'scanner_endpoint_discovery',
    'scanner_v4',
    'scanner_v6',
    'scanner',
    'scanner_qualys',
    'scanner_dns',
    'scanner_ipv4_only',
]

# define roles for workers
WORKER_QUEUE_CONFIGURATION = {
    # universal worker that has access to database and internet
    'default': [
        # for tasks that require network connectivity to perform a scanning task
        Queue('scanners'),
        # allow to differentiate on scan tasks that have specific ip network family requirements
        Queue('scanners.ipv4'),
        Queue('scanners.ipv6'),
        # a special queue for Qualys as it requires rate limiting and that causes other tasks in
        # the same queue to stall.
        Queue('scanners.qualys'),
        # for tasks that require a database connection
        Queue('storage'),
        # default queue for task with no explicit queue assigned
        # these tasks should not expect network connectivity or database access!
        Queue('default'),
        # legacy default queue, can be removed after transition period to multiworkers
        Queue('celery'),
        # endpoint discovery
        Queue('scanners.endpoint_discovery.ipv4'),
        Queue('scanners.endpoint_discovery.ipv6'),
        Queue('scanners.dns'),
    ],
    # universal worker without ipv6 specific queues
    'default_ipv4': [
        Queue('scanners'),
        Queue('scanners.ipv4'),
        Queue('scanners.qualys'),
        Queue('storage'),
        Queue('default'),
        Queue('celery'),
        Queue('scanners.endpoint_discovery.ipv4'),
        Queue('scanners.dns'),
    ],
    # special queue for handling tons of tasks that are rate limited (we don't want to broadcast
    # hundreds of thousands of tasks at the same time since that looks like hostile internet traffic)
    'scanner_endpoint_discovery': [
        Queue('scanners.endpoint_discovery.ipv4'),
        Queue('scanners.endpoint_discovery.ipv6'),
    ],
    'scanner_v4': [
        Queue('scanners.ipv4'),
        Queue('scanners.endpoint_discovery.ipv4'),
    ],
    'scanner_v6': [
        Queue('scanners.ipv6'),
        Queue('scanners.endpoint_discovery.ipv6'),
    ],
    # worker with access to storage allowed to connect to databases
    'storage': [
        Queue('storage'),
        Queue('default'),
        Queue('celery'),
    ],
    # universal scanner worker that has internet access for both IPv4 and IPv6
    'scanner': [
        Queue('scanners'),
        Queue('scanners.ipv4'),
        Queue('scanners.ipv6'),
    ],
    # special scanner worker for qualys rate limited tasks to not block queue for other tasks
    'scanner_qualys': [
        Queue('scanners.qualys'),
    ],
    # special scanner worker to handle tons of dns queries
    'scanner_dns': [
        Queue('scanners'),
        Queue('scanners.dns'),
    ],
    # scanner with no IPv6 connectivity
    # this is an initial concept and can later be replaced with universal
    # scanner that automatically detects connectivity
    'scanner_ipv4_only': [
        Queue('scanners'),
        Queue('scanners.ipv4'),
    ],
}


def worker_configuration():
    """Apply specific configuration for worker depending on environment."""

    role = os.environ.get('WORKER_ROLE', 'default')

    log.info('Configuring worker for role: %s', role)

    # configure which queues should be consumed depending on assigned role for this worker
    return {'task_queues': WORKER_QUEUE_CONFIGURATION[role]}


def worker_verify_role_capabilities(role):
    """Determine if chosen role can be performed on this host (eg: ipv6 connectivity.)"""

    if role in IPV6_ROLES:
        # verify if a https connection to a IPv6 website can be made
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM, 0)
        try:
            s.connect((IPV6_TEST_DOMAIN, 443))
        except BaseException:
            log.warning('Failed to connect to ipv6 test domain %s via IPv6', IPV6_TEST_DOMAIN, exc_info=True)
            return False

    if role in CONNECTIVITY_ROLES:
        # verify if a https connection to a website can be made
        # we assume non-ipv4 internet doesn't exist
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        try:
            s.connect((CONNECTIVITY_TEST_DOMAIN, 443))
        except BaseException:
            log.warning('Failed to connect to test domain %s', CONNECTIVITY_TEST_DOMAIN, exc_info=True)
            return False

    return True


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
