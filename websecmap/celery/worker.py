"""
A worker gets a role from it's configuration. This role determines which queue's are processed by the worker.
The role also specifies what network connectivity is required (ipv4, ipv6 or both).

A normal websecmap server should have both IPv4 and IPv6 access.

On tricky issue:
The ROLE scanner requires both access to IPv4 and IPv6 networks.
The QUEUE scanner contains tasks that do not care about network family and can be either 4 or 6.
"""

import logging
import os
import socket

from constance import config
from kombu import Queue
from retry import retry

log = logging.getLogger(__name__)

# list of all roles that require internet connectivity
ROLES_REQUIRING_ANY_NETWORK = [
    "internet",  # the queue scanner accepts 4and6, 4 or 6 - so ANY network scan :)
]

ROLES_REQUIRING_IPV4_AND_IPV6 = ["default", "all_internet"]

# list of all roles that require IPv6 networking
ROLES_REQUIRING_IPV6 = [
    "v6_internet",
    "default_ipv6",
]

ROLES_REQUIRING_IPV4 = [
    "v4_internet",
    "default_ipv4",
    "qualys",  # only supports ipv4(!)
]

ROLES_REQUIRING_NO_NETWORK = [
    "storage",
    "calculator",
    "claim_proxy",
    "reporting",
]

ROLES_REQUIRING_GUI_AND_NETWORK = ["desktop"]

# define roles for workers
QUEUES_MATCHING_ROLES = {
    # Select between roles.
    # universal worker that has access to database and internet on both v4 and v6
    # will work in one-worker configuration - and slowly -  it's untested and it likely will not be a great experience
    "default": [
        # doesn't care about network family, any network is fine
        Queue("internet"),
        # only ipv4 tasks
        Queue("ipv4"),
        # only ipv4 tasks
        Queue("ipv6"),
        # needs both network families to be present
        Queue("4and6"),
        # for tasks that require a database connection
        Queue("storage"),
        # tasks that require no network, no database. Such as calculations, parsing of datasets etc.
        Queue("isolated"),
        # run qualys scans
        Queue("qualys"),
        Queue("claim_proxy"),
        Queue("reporting"),
        Queue("discover_subdomains"),
        Queue("known_subdomains"),
        Queue("screenshot"),
    ],
    # queuemonitor shows the currently running queues on the dashboard. It will not do anything else. It subscribes
    # to all queues. This does not have a worker (and doesn't need one).
    "queuemonitor": [
        Queue("storage"),
        Queue("4and6"),
        Queue("ipv4"),
        Queue("ipv6"),
        Queue("internet"),
        Queue("qualys"),
        Queue("isolated"),
        Queue("claim_proxy"),
    ],
    "default_ipv4": [
        Queue("internet"),
        Queue("ipv4"),
        Queue("storage"),
        Queue("isolated"),
    ],
    "default_ipv6": [
        Queue("internet"),
        Queue("ipv6"),
        Queue("storage"),
        Queue("isolated"),
    ],
    "v4_internet": [
        Queue("internet"),
        Queue("ipv4"),
        Queue("isolated"),
    ],
    "v6_internet": [
        Queue("internet"),
        Queue("ipv6"),
        Queue("isolated"),
    ],
    "storage": [
        Queue("storage"),
        # Queue('isolated'),  # Do NOT perform isolated (slow) tasks, which might block the worker.
        # Given there is only one storage worker, blocking it doesn't help it's work.
    ],
    "reporting": [
        Queue("reporting"),
    ],
    "claim_proxy": [
        Queue("claim_proxy"),
        # Queue('isolated'),  # Do NOT perform isolated (slow) tasks, which might block the worker.
        # Given there is only one storage worker, blocking it doesn't help it's work.
    ],
    "calculator": [Queue("isolated")],
    "desktop": [Queue("desktop")],
    # universal scanner worker that has internet access for either IPv4 and IPv6 or both (you don't know)
    "any_internet": [
        Queue("internet"),  # tasks that requires ANY network
        Queue("isolated"),  # no network, no database
    ],
    # all internet access, with ipv4 and 6 configured
    "all_internet": [
        Queue("internet"),
        Queue("ipv4"),
        Queue("ipv6"),
        Queue("4and6"),
        Queue("isolated"),
    ],
    # special scanner worker for qualys rate limited tasks to not block queue for other tasks
    # and it needs a dedicated IP address, which is coded in hyper workers.
    "qualys": [
        Queue("qualys"),
    ],
    "discover_subdomains": [
        Queue("discover_subdomains"),
    ],
    "known_subdomains": [
        Queue("known_subdomains"),
    ],
    "screenshot": [
        Queue("screenshot"),
    ],
}


def worker_configuration():
    """Apply specific configuration for worker depending on environment."""

    role = os.environ.get("WORKER_ROLE", "default")

    log.info("Configuring worker for role: %s", role)

    # configure which queues should be consumed depending on assigned role for this worker
    return {"task_queues": QUEUES_MATCHING_ROLES[role]}


@retry(tries=3, delay=5)
def worker_verify_role_capabilities(role):
    """Determine if chosen role can be performed on this host (eg: ipv6 connectivity.)"""

    failed = False

    if role in ROLES_REQUIRING_NO_NETWORK:
        return not failed

    if role in ROLES_REQUIRING_IPV6 or role in ROLES_REQUIRING_IPV4_AND_IPV6:
        # allow IPv6 support to be faked during development
        if not os.environ.get("NETWORK_SUPPORTS_IPV6", False):
            # verify if a https connection to a IPv6 website can be made
            s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM, 0)
            try:
                s.connect((config.IPV6_TEST_DOMAIN, 443))
            except socket.gaierror:
                # docker container DNS might not be ready, retry
                raise
            except BaseException:
                log.warning("Failed to connect to ipv6 test domain %s via IPv6", config.IPV6_TEST_DOMAIN, exc_info=True)
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
            log.warning("Failed to connect to test domain %s via IPv4", config.CONNECTIVITY_TEST_DOMAIN, exc_info=True)
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
                log.warning(
                    "Failed to connect to test domain %s via both v6 and v6",
                    config.CONNECTIVITY_TEST_DOMAIN,
                    exc_info=True,
                )
                failed = True

    return not failed
