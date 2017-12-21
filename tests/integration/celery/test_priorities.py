"""Test/prove some assumtions about celery behaviour (eg: priorities)."""

# The concurrent nature of this test and the parts its testing can cause this
# test to be 'flaky' (fail/succeed at random) and non-deterministic.
# Parameters for this test are to be carefully choosen to not introduce flaky
# behaviour which invalidates the results of this test.
# For example a to low number of samples might cause

import time

from celery.result import ResultSet
from django.conf import settings

from failmap_admin.celery import PRIO_HIGH, app

# amount of time the dummy task 'runs'
SLEEP = 0.1

# amount of tasks to use for this test should always be able to saturate concurrent workers
# and not cause flaky test behaviour when a infinite prefetch is used (ie: it should be high)
SAMPLES = settings.CELERY_WORKER_CONCURRENCY * settings.CELERY_WORKER_CONCURRENCY

assert SAMPLES > 10, 'with current settings this test might not provide reliable results!'


@app.task
def waitsome():
    """Wait some time and return epoch at completion."""

    time.sleep(SLEEP)
    return time.time()


def test_high_priority(celery_app, celery_worker):
    """High prio tasks should be executed first."""

    TASK_EXPIRY_TIME = SAMPLES * SLEEP

    # enqueue normal and high prio tasks alternately
    high, normal = [], []
    for index in range(SAMPLES):
        if index % 2:
            normal.append(waitsome.apply_async(expires=TASK_EXPIRY_TIME))
        else:
            high.append(waitsome.apply_async(expires=TASK_EXPIRY_TIME, priority=PRIO_HIGH))

    # wait for all tasks to complete
    print(ResultSet(results=high + normal).join(timeout=TASK_EXPIRY_TIME))
    results_high = ResultSet(results=high).join()
    results_normal = ResultSet(results=normal).join()

    # determine amount of earlier executed normal prio tasks
    last_high_prio = sorted(results_high)[-1]
    early_normal = len([r for r in results_normal if r <= last_high_prio])

    # amount of normal priority tasks executed earlier then the last executed high prio task
    # should ideally be 0 but surely not be greater than the amount of concurrent worker threads
    # give or take 3 amounts to account for early/late task race conditions
    # ie: some interlaced normal prio tasks get picked up by a worker thread because there are
    # no high prio tasks available at that time
    assert early_normal < (3 * settings.CELERY_WORKER_CONCURRENCY)
