"""Import modules containing tasks that need to be auto-discovered by Django Celery."""
import logging

from celery import states

from failmap.celery import app

from . import (scanner_dnssec, scanner_dummy, scanner_http, scanner_security_headers,
               scanner_tls_qualys)

# explicitly declare the imported modules as this modules 'content', prevents pyflakes issues
__all__ = [scanner_tls_qualys, scanner_security_headers, scanner_dummy, scanner_http, scanner_dnssec]

logger = logging.getLogger(__package__)


@app.task(
    bind=True,
    rate_limit='30/s',
)
def every_two_minutes(self, counter: int):
    logger.info("Task triggered %s!" % counter)

    state = self.AsyncResult(self.request.id).state
    if state in [states.PENDING, states.STARTED]:
        logger.info("Started first attempt to do something. State: %s " % state)
    if state == states.RETRY:
        logger.info("Task retried...")

    raise self.retry(countdown=10, priorty=5, max_retries=2, queue='scanners.qualys')
