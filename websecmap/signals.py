"""This module is imported by failmap.__init__ to register Signal hooks."""
import logging
import os
import platform
import sys

from celery.signals import celeryd_init

from websecmap.celery.worker import worker_configuration, worker_verify_role_capabilities

log = logging.getLogger(__name__)


@celeryd_init.connect
def configure_workers(sender=None, conf=None, instance=None, **kwargs):
    """Configure workers when Celery is initialized."""

    # set hostname based on context
    container_host_name = os.environ.get("HOST_HOSTNAME", None)
    if container_host_name:
        hostname = ".".join([platform.node(), container_host_name])
    else:
        hostname = platform.node()
    role = os.environ.get("WORKER_ROLE", "default")
    instance.hostname = "%s@%s" % (role, hostname)

    if not worker_verify_role_capabilities(role):
        log.error("Host does not seem to have capabilities to run chosen role!")
        sys.exit(1)
    log.info("Worker is capable for chosen role.")

    try:
        # configure worker queues
        conf.update(worker_configuration())
    except BaseException:
        log.exception("Failed to setup worker configuration!")
        sys.exit(1)
