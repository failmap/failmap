"""Import modules containing tasks that need to be auto-discovered by Django Celery."""
import logging

from celery import group, states
from celery.result import allow_join_result

from failmap.celery import app

from . import (scanner_dns, scanner_dnssec, scanner_dummy, scanner_ftp, scanner_http,
               scanner_plain_http, scanner_security_headers, scanner_tls_osaft, scanner_tls_qualys)

# explicitly declare the imported modules as this modules 'content', prevents pyflakes issues
__all__ = [scanner_tls_qualys, scanner_security_headers, scanner_dummy, scanner_http, scanner_dnssec, scanner_ftp,
           scanner_tls_osaft]

# This is the single source of truth regarding scanner configuration.
# Lists to be used elsewhere when tasks need to be composed, these lists contain compose functions.
# Other code can iterate over these functions and call them, example: see onboard.py.
TLD_DEFAULT_ONBOARDERS = []
DEFAULT_ONBOARDERS = [scanner_http.compose_task]
TLD_DEFAULT_CRAWLERS = [
    scanner_dns.brute_known_subdomains_compose_task,
    scanner_dns.certificate_transparency_compose_task,
    scanner_dns.nsec_compose_task]
DEFAULT_CRAWLERS = []
DEFAULT_SCANNERS = [
    scanner_plain_http.compose_task,
    scanner_security_headers.compose_task,
    scanner_tls_qualys.compose_task]
TLD_DEFAULT_SCANNERS = [scanner_dnssec.compose_task]

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


@app.task(bind=True)
def slow_task(self, counter: int):
    import time
    logger.warning("slow task %s started" % counter)
    time.sleep(10)
    logger.warning("slow task %s finished" % counter)


@app.task
def second_part():
    tasks = [slow_task.si(4), slow_task.si(5), slow_task.si(6)]
    task = group(tasks)
    task.apply_async()


@app.task
def first_part():
    tasks = [slow_task.si(1), slow_task.si(2), slow_task.si(3)]
    task = group(tasks)
    res = task.apply_async()

    # we MUST wait until these tasks have finished before continuing. So this will be blocking.
    # https://stackoverflow.com/questions/45490722/runtimeerror-never-call-result-get-within-a-task-celery
    # This also works in chains, as well as chords.
    with allow_join_result():
        res.get(on_message="")

    return True
