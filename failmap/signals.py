"""This module is imported by failmap.__init__ to register Signal hooks."""

from celery.signals import celeryd_init

from .celery.worker import worker_configuration


@celeryd_init.connect
def configure_workers(sender=None, conf=None, **kwargs):
    """Configure workers when Celery is initialized."""

    worker_configuration(conf)
