"""Test assumptions about rate limiting."""

import time

from django.conf import settings

from failmap.celery import rate_limited, waitsome

SAMPLES = settings.CELERY_WORKER_CONCURRENCY * 2
SLEEP = 5

TASK_EXPIRY_TIME = SAMPLES * SLEEP


def test_rate_limits(celery_app, celery_worker, queue):
    """Rate limited tasks should not hold up worker queue for other tasks."""
    # fill queue with rate limited tasks
    rated_tasks = [
        rate_limited.apply_async([SLEEP], queue=queue, expires=TASK_EXPIRY_TIME) for _ in range(SAMPLES)]
    time.sleep(SLEEP / 2)

    # add tasks that is not rate limited
    task = waitsome.apply_async([0], queue=queue, expires=TASK_EXPIRY_TIME)

    # make sure task is executed before all rate limited tasks are done
    assert task.get(timeout=SLEEP)

    # for sanity make sure not more than half the rate limited task have been executed in the mean time
    PENDING_RATED_TASKS = len([s for s in rated_tasks if s.state == 'PENDING'])
    assert PENDING_RATED_TASKS > SAMPLES / 2
