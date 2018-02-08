"""This module is imported by failmap.__init__ to register Signal hooks."""

import shutil
import tempfile

from celery.signals import celeryd_init, worker_shutdown
from django.conf import settings

from .celery.worker import tls_client_certificate, worker_configuration


@celeryd_init.connect
def configure_workers(sender=None, conf=None, **kwargs):
    """Configure workers when Celery is initialized."""

    # create a universal temporary directory to be removed when the application quits
    settings.WORKER_TMPDIR = tempfile.mkdtemp()

    # configure worker queues
    worker_configuration(conf)

    # for remote workers configure TLS key and certificate from PKCS12 file
    tls_client_certificate(conf)


@worker_shutdown.connect
def cleanup_certificates(sender=None, conf=None, **kwargs):
    """Remove worker temporary directory."""

    shutil.rmtree(settings.WORKER_TMPDIR)
