"""Shared fixtures used by different tests."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from websecmap.celery import waitsome
import logging

TIMEOUT = 30
log = logging.getLogger(__package__)


@pytest.fixture
def current_path():
    path = Path(__file__).parent
    yield path


@pytest.fixture(scope="session")
def faaloniae_integration():
    """Load test organization fixtures."""

    log.debug("Loading faalonie dataset")
    subprocess.call(["websecmap", "migrate"])
    subprocess.call(["websecmap", "load_dataset", "faalonie"])


@pytest.fixture(scope="session", params=["prefork", "eventlet"])
def worker(request):
    """Run a task worker instance."""

    pool = request.param

    worker_command = ["websecmap", "celery", "worker", "-l", "info", "--pool", pool]
    worker_env = dict(os.environ, WORKER_ROLE="default_ipv4")
    worker_process = subprocess.Popen(
        worker_command, stdout=sys.stdout.buffer, stderr=sys.stderr.buffer, preexec_fn=os.setsid, env=worker_env
    )
    # wrap assert in try/finally to kill worker on failing assert, wrap yield as well for cleaner code
    try:
        # wait for worker to start accepting tasks before turning to test function
        assert waitsome.apply_async([0], expires=TIMEOUT).get(
            timeout=TIMEOUT
        ), "Worker failed to become ready and execute test task."
        # give worker stderr time to output into 'Captured stderr setup' and not spill over into 'Captured stderr call'
        time.sleep(0.1)
        yield worker_process
    finally:
        # stop worker and all child threads
        os.killpg(os.getpgid(worker_process.pid), signal.SIGKILL)
