# https://realpython.com/blog/python/asynchronous-tasks-with-django-and-celery/
# https://github.com/failmap/failmap/pull/2/files
# http://oddbird.net/2017/03/20/serializing-things/
# http://docs.celeryproject.org/en/latest/userguide/security.html

import os
import time

from celery import Celery, Task
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "failmap.settings")

app = Celery(__name__)
app.config_from_object('django.conf:settings', namespace='CELERY')
# autodiscover all celery tasks in tasks.py files inside failmap modules
appname = __name__.split('.', 1)[0]
app.autodiscover_tasks([app for app in settings.INSTALLED_APPS if app.startswith(appname)])

# http://docs.celeryproject.org/en/master/whatsnew-4.0.html?highlight=priority#redis-priorities-reversed
# http://docs.celeryproject.org/en/master/history/whatsnew-3.0.html?highlight=priority
# priorities 0-9 are divided into 4 steps.
# https://github.com/celery/celery/blob/a87ef75884e59c78da21b1482bb66cf649fbb7d3/docs/history/whatsnew-3.0.rst#redis-priority-support
# https://github.com/celery/celery/blob/f83b072fba7831f60106c81472e3477608baf289/docs/whatsnew-4.0.rst#redis-priorities-reversed
# contrary to 'documentation' in release notes the redis priorities do not seem aligned with rabbitmq
if 'redis://' in app.conf.broker_url:
    PRIO_HIGH = 0
    PRIO_NORMAL = 5
    PRIO_LOW = 9
else:
    PRIO_HIGH = 9
    PRIO_NORMAL = 5
    PRIO_LOW = 0


class DefaultTask(Task):
    """Default settings for all failmap tasks."""

    priority = PRIO_NORMAL


app.Task = DefaultTask


class ParentFailed(Exception):
    """Error to indicate parent task has failed."""

    def __init__(self, message, *args, cause=None):
        """Allow to set parent exception as cause."""
        if cause:
            self.__cause__ = cause
        super(ParentFailed, self).__init__(message, *args)


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))


@app.task
def waitsome(sleep):
    """Wait some time and return epoch at completion."""

    time.sleep(sleep)
    return time.time()


@app.task(rate_limit='1/s')
def rate_limited(sleep):
    """Wait some time but limit to maximum tasks of 1 per second."""

    time.sleep(sleep)
    return time.time()
