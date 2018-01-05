"""Shared fixtures used by different tests."""
import os
import signal
import subprocess
import sys
import time

import pytest

from failmap.celery import waitsome

TIMEOUT = 5


@pytest.fixture(scope="session")
def faalonië():
    """Load test organization fixtures."""

    subprocess.call(['failmap', 'load_dataset', 'faalonië'])


@pytest.fixture(scope="session")
def worker():
    """Run a task worker instance."""
    worker_command = ['failmap', 'celery', 'worker', '-l', 'info']
    worker_process = subprocess.Popen(worker_command,
                                      stdout=sys.stdout.buffer, stderr=sys.stderr.buffer,
                                      preexec_fn=os.setsid)
    # wrap assert in try/finally to kill worker on failing assert, wrap yield as well for cleaner code
    try:
        # wait for worker to start accepting tasks before turning to test function
        assert waitsome.apply_async([0], expires=TIMEOUT).get(timeout=TIMEOUT), \
            "Worker failed to become ready and execute test task."
        # give worker stderr time to output into 'Captured stderr setup' and not spill over into 'Captured stderr call'
        time.sleep(0.1)
        yield worker_process
    finally:
        # stop worker and all child threads
        os.killpg(os.getpgid(worker_process.pid), signal.SIGKILL)
