"""
This helps with creating experiments and learning to work with Celery, redis and it's quirks. It gives some insights
in the things we're doing in failmap.
"""

import logging

from celery import chain, group, states
from celery.result import allow_join_result

from failmap.celery import app

log = logging.getLogger(__package__)


@app.task(
    bind=True,
    rate_limit='30/s',
)
@app.task(queue='storage')
def dummy_task():
    log.error("Nothing is going wrong here...")


def every_two_minutes(self, counter: int):
    log.info("Task triggered %s!" % counter)

    state = self.AsyncResult(self.request.id).state
    if state in [states.PENDING, states.STARTED]:
        log.info("Started first attempt to do something. State: %s " % state)
    if state == states.RETRY:
        log.info("Task retried...")

    raise self.retry(countdown=10, priorty=5, max_retries=2, queue='scanners.qualys')


@app.task(bind=True)
def slow_task(self, counter: int):
    import time
    log.warning("slow task %s started" % counter)
    time.sleep(10)
    log.warning("slow task %s finished" % counter)


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


def run_sequential_groups():
    # tasks.append(chain(group(explore), callback)) does not wait for the first tasks to finish(!)
    # a chord does also NOT wait for tasks to finish... wtf
    # or wait: the task of making the other tasks has finished...

    # we want to make sure tasks 4, 5, 6 are running AFTER 1 2 and 3
    callback = second_part.si()
    header = first_part.si()

    # tasks = chord(header)(callback)
    tasks = chain(header, callback)

    task = group(tasks)
    print(task)
    tasks.apply_async()
