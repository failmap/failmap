import os
import signal
import subprocess
import sys

import pytest

from failmap_admin.celery import app


@pytest.fixture()
def celery_app():
    yield app


@pytest.fixture(scope='session')
def celery_worker():
    worker_command = ['failmap-admin', 'celery', 'worker', '-l', 'info']
    worker_process = subprocess.Popen(worker_command,
                                      stdout=sys.stdout.buffer, stderr=sys.stderr.buffer,
                                      preexec_fn=os.setsid)
    yield worker_process
    worker_process.terminate()
    os.killpg(os.getpgid(worker_process.pid), signal.SIGTERM)


@pytest.fixture(scope='session')
def celery_worker_pool():
    """Align test worker settings with project settings."""
    return 'prefork'
