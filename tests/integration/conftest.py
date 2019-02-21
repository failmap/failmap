import logging
import os
import signal
import subprocess
import sys
import time

import pytest

from websecmap.celery import app, waitsome

log = logging.getLogger(__name__)


TIMEOUT = 60


@pytest.fixture()
def queues():
    """Generate a unique queue to isolate every test."""
    yield ['queue-' + str(time.time()), 'queue2-' + str(time.time())]


@pytest.fixture()
def celery_app():
    yield app


@pytest.fixture(params=['prefork', 'eventlet'])
def celery_worker(queues, request):
    """Spawn celery worker to be used during test.

    This worker only listens on specified queues to ensure test integrity!

    Tests on both implementations of worker."""
    pool = request.param

    worker_command = [
        'failmap',
        'celery',
        'worker',
        '-l', 'info',
        '--pool', pool,
        '--queues', ','.join(queues)
    ]
    worker_env = dict(os.environ, WORKER_ROLE='default_ipv4')

    log.info('Running worker with: %s', ' '.join(worker_command))
    worker_process = subprocess.Popen(worker_command,
                                      stdout=sys.stdout.buffer, stderr=sys.stderr.buffer,
                                      preexec_fn=os.setsid, env=worker_env)
    # wrap assert in try/finally to kill worker on failing assert, wrap yield as well for cleaner code
    try:
        # wait for worker to start accepting tasks before turning to test function
        assert waitsome.apply_async([0], queue=queues[0], expires=TIMEOUT).get(timeout=TIMEOUT), \
            "Worker failed to become ready and execute test task."
        # give worker stderr time to output into 'Captured stderr setup' and not spill over into 'Captured stderr call'
        time.sleep(0.1)
        yield worker_process
    finally:
        # stop worker and all child threads
        os.killpg(os.getpgid(worker_process.pid), signal.SIGKILL)
