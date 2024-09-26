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
from sentry_sdk import set_tag

log = logging.getLogger(__name__)

WORKER_ROLE = os.environ.get("WORKER_ROLE", "default")


# list of all roles that require internet connectivity
ROLES_REQUIRING_ANY_NETWORK = [
    "internet",  # the queue scanner accepts 4and6, 4 or 6 - so ANY network scan :)
]

ROLES_REQUIRING_IPV4_AND_IPV6 = ["default", "all_internet", "bannergrab", "amass", "prefork"]

# list of all roles that require IPv6 networking
ROLES_REQUIRING_IPV6 = [
    "alt_v6_internet",
    "v6_internet",
    "default_ipv6",
]

ROLES_REQUIRING_IPV4 = [
    "alt_v4_internet",
    "v4_internet",
    "default_ipv4",
    "qualys",  # only supports ipv4(!)
    "playwright-privacy",
]

ROLES_REQUIRING_NO_NETWORK = [
    "storage",
    "kickoff",
    "calculator",
    "claim_proxy",
    "reporting",
]

ROLES_REQUIRING_GUI_AND_NETWORK = ["desktop"]

# define roles for workers
QUEUES_MATCHING_ROLES = {
    # some queue descriptions:
    #     # doesn't care about network family, any network is fine
    #     Queue("internet"),
    #     # only ipv4 tasks, but this is kinda broken since this worker will run dual-stack
    #     Queue("ipv4"),
    #     # only ipv6 tasks, but this is kinda broken since this worker will run dual-stack
    #     Queue("ipv6"),
    #     # needs both network families to be present
    #     Queue("4and6"),
    #     # Queue used at the end of a task to store the results
    #     Queue("storage"),
    #     # for tasks that require db connection for reading and writing
    #     # TODO: ideally a minimal amount of tasks should use this queue as tasks should get all their input
    #     # handed to them and output to a 'store' task. But sometimes it might be better for performance to
    #     # read and write to the DB, eg: generating reports.
    #     Queue("database"),
    #     # queue for tasks that talk with the DB now, but should be rewritten to not do that, se TODO above
    #     Queue("database_deprecate"),
    #     # celery internal maintenance (eg: remove expired results)
    #     Queue("celery"),
    #     # run qualys scans
    #     Queue("qualys"),
    #     Queue("claim_proxy"),
    #     Queue("reporting"),
    #     Queue("discover_subdomains"),
    #     Queue("known_subdomains"),
    #     Queue("screenshot"),
    #     Queue("kickoff"),
    #     Queue("playwright-privacy"),
    #     Queue("cookie-consent"),
    #     Queue("prefork"),
    #     Queue("amass"),
    #     Queue("bannergrab"),
    #     Queue("followupscan"),
    #     Queue("nucleiv4"),
    #     Queue("nucleiv6"),
    # Select between roles.
    # queuemonitor shows the currently running queues on the dashboard. It will not do anything else. It subscribes
    # to all queues. This does not have a worker (and doesn't need one).
    "queuemonitor": [
        Queue("storage"),
        Queue("4and6"),
        Queue("ipv4"),
        Queue("ipv6"),
        Queue("internet"),
        Queue("qualys"),
        Queue("claim_proxy"),
    ],
    "default_ipv4": [
        Queue("internet"),
        Queue("ipv4"),
        Queue("storage"),
    ],
    "default_ipv6": [
        Queue("internet"),
        Queue("ipv6"),
        Queue("storage"),
    ],
    # workers limited to IPv4 or IPv6 traffic by configuratie and firewall
    "v4_internet": [
        # accept only tasks that need ipv4-only network
        Queue("ipv4"),
    ],
    "v6_internet": [
        # accept only tasks that need ipv6-only network
        Queue("ipv6"),
    ],
    "v4_nuclei": [
        # accept only tasks that need ipv4-only network
        Queue("nucleiv4"),
    ],
    "v6_nuclei": [
        # accept only tasks that need ipv6-only network
        Queue("nucleiv6"),
    ],
    # all internet access, with ipv4 and 6 configured
    "all_internet": [
        Queue("internet"),
    ],
    "storage": [
        # Queue used at the end of a task to store the results
        Queue("storage"),
    ],
    "database": [
        # for tasks that require db connection for reading and writing
        # TODO: ideally a minimal amount of tasks should use this queue as tasks should get all their input
        # handed to them and output to a 'store' task. But sometimes it might be better for performance to
        # read and write to the DB, eg: generating reports.
        Queue("database"),
        # queue for tasks that talk with the DB now, but should be rewritten to not do that, se TODO above
        Queue("database_deprecate"),
        # celery internal maintenance (eg: remove expired results)
        Queue("celery"),
    ],
    # this is where tasks are started: scans are planned and added to the rest to the worker.
    # storage is used for storing after you're done
    "kickoff": [
        Queue("kickoff"),
    ],
    "reporting": [
        Queue("reporting"),
    ],
    "claim_proxy": [
        Queue("claim_proxy"),
        # Queue('isolated'),  # Do NOT perform isolated (slow) tasks, which might block the worker.
        # Given there is only one storage worker, blocking it doesn't help it's work.
    ],
    "desktop": [Queue("desktop")],
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
    "followupscan": [
        Queue("followupscan"),
    ],
    "bannergrab": [
        Queue("bannergrab"),
    ],
    "playwright-privacy": [
        Queue("playwright-privacy"),
    ],
    "cookie-consent": [
        Queue("cookie-consent"),
    ],
    "amass": [
        Queue("amass"),
    ],
    "prefork": [
        Queue("prefork"),
    ],
}

# universal worker that has access to database and internet on both v4 and v6
# will work in one-worker configuration - and slowly -  it's untested and it likely will not be a great experience
# This is useful for development, so it perhaps should be named 'development' instead of default?
# The sum flattens the list of lists: .
QUEUES_MATCHING_ROLES["default"] = set(sum(QUEUES_MATCHING_ROLES.values(), []))


def worker_configuration():
    """Apply specific configuration for worker depending on environment."""

    log.info("Configuring worker for role: %s", WORKER_ROLE)

    set_tag("worker_role", WORKER_ROLE)

    # configure which queues should be consumed depending on assigned role for this worker
    # fall back to storage if the queue is not defined above, to prevent crashes
    return {"task_queues": QUEUES_MATCHING_ROLES.get(WORKER_ROLE, QUEUES_MATCHING_ROLES["storage"])}


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
            if not connect_socket(socket.AF_INET6, config.IPV6_TEST_DOMAIN):
                failed = True

    if role in ROLES_REQUIRING_IPV4 or role in ROLES_REQUIRING_IPV4_AND_IPV6:
        # verify if a https connection to a website can be made
        # we assume non-ipv4 internet doesn't exist
        if not connect_socket(socket.AF_INET, config.CONNECTIVITY_TEST_DOMAIN):
            failed = True

    if role in ROLES_REQUIRING_ANY_NETWORK:
        # one may fail.
        if not connect_socket(socket.AF_INET, config.IPV6_TEST_DOMAIN):
            if not connect_socket(socket.AF_INET6, config.IPV6_TEST_DOMAIN):
                failed = True

    return not failed


def connect_socket(inet, domain: str):
    # socket.AF_INET
    my_socket = socket.socket(inet, socket.SOCK_STREAM, 0)
    try:
        my_socket.connect((domain, 443))
        return True
    except socket.gaierror:
        # docker container DNS might not be ready, retry
        raise
    # a million things can go wrong with sockets, and do we really care?
    except BaseException:  # pylint: disable=broad-except
        log.warning("Failed to connect to test domain %s via IPv4/6 %s", domain, inet, exc_info=True)
        return False
