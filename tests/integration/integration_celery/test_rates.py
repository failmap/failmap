"""Test assumptions about rate limiting."""

import time

import pytest
from django.conf import settings

from websecmap.celery import rate_limited, waitsome

SAMPLES = settings.CELERY_WORKER_CONCURRENCY * settings.CELERY_WORKER_CONCURRENCY
SLEEP = 5

TASK_EXPIRY_TIME = SAMPLES * SLEEP


@pytest.mark.skip(reason="Test is unreliable and problem can't currently be fixed without multiple workers.")
def test_rate_limits(celery_app, celery_worker, queues):
    """Rate limited tasks should not hold up worker queue for other tasks.

    Rate limited task are put into a different queue as this seems the only way currently to allow this behaviour.
    """
    # fill queue with rate limited tasks
    rated_tasks = [
        rate_limited.apply_async([SLEEP], queue=queues[0], expires=TASK_EXPIRY_TIME) for _ in range(SAMPLES)]
    time.sleep(1)

    # add tasks that is not rate limited
    task = waitsome.apply_async([0], queue=queues[1], expires=TASK_EXPIRY_TIME)

    # make sure task is executed before all rate limited tasks are done
    assert task.get(timeout=1)

    # for sanity make sure not more than half the rate limited task have been executed in the mean time
    PENDING_RATED_TASKS = len([s for s in rated_tasks if s.state == 'PENDING'])
    assert PENDING_RATED_TASKS > SAMPLES / 2
