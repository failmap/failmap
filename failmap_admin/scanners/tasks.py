"""Binds the function logic into queue logic."""

import logging

from django.apps import apps

from ..celery import app
from .scanners import ThisScannerFailedException, blascanner

log = logging.getLogger(__name__)

RETRY_INTERVAL = 60


@app.task
def task_store_scanresult(result, model_name, obj_id):
    """Store a scanresult in the respective model.

    Celery task.
    """

    model = apps.get_model('scanners', model_name)
    obj = model.objects.get(id=obj_id)

    obj.update(**result)
    obj.update(state='FINISHED')


@app.task(bind=True)
def task_blascanner(self, domain):
    """Example celery scanner task implementation."""

    try:
        result = blascanner(domain)
    except ThisScannerFailedException as exc:
        log.exception('the scanner failed, retrying')
        self.retry(exc=exc, countdown=RETRY_INTERVAL)
    except TimeoutError as exc:
        log.exception('the scanner timed out, retry asap')
        self.retry(exc=exc, countdown=0)

    return result
