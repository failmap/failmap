import os
import signal
import subprocess
import sys
import time

import pytest

from failmap.celery import app, waitsome

TIMEOUT = 30


@pytest.fixture()
def queue():
    """Generate a unique queue to isolate every test."""
    yield 'queue-' + str(time.time())


@pytest.fixture()
def celery_app():
    yield app


@pytest.fixture()
def celery_worker(queue):
    worker_command = ['failmap', 'celery', 'worker', '-l', 'info', '--queues', queue]
    worker_process = subprocess.Popen(worker_command,
                                      stdout=sys.stdout.buffer, stderr=sys.stderr.buffer,
                                      preexec_fn=os.setsid)
    # wait for worker to start accepting tasks before turning to test function
    assert waitsome.apply_async([0], queue=queue, expires=TIMEOUT).get(timeout=TIMEOUT)
    print('worker ready', file=sys.stderr)
    yield worker_process

    # stop worker and all child threads
    os.killpg(os.getpgid(worker_process.pid), signal.SIGKILL)
