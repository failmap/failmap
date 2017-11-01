# https://realpython.com/blog/python/asynchronous-tasks-with-django-and-celery/
# https://github.com/failmap/admin/pull/2/files
# http://oddbird.net/2017/03/20/serializing-things/
# http://docs.celeryproject.org/en/latest/userguide/security.html

import os

import celery.exceptions
from celery import Celery, Task
from django.conf import settings

import celery_statsd

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "failmap_admin.settings")

app = Celery(__name__)
app.config_from_object('django.conf:settings')
# autodiscover all celery tasks in tasks.py files inside failmap_admin modules
appname = __name__.split('.', 1)[0]
app.autodiscover_tasks([app for app in settings.INSTALLED_APPS if app.startswith(appname)])


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))


class ExceptionPropagatingTask(Task):
    """Task baseclass that propagates exceptions down the chain as results."""

    def __call__(self, *args, **kwargs):
        """Wrap task run to propagate Exception down the chain and to reraise exception if it is passed as argument."""
        # If any of the arguments is an Exception reraise this adding current task for context.
        for arg in args:
            if isinstance(arg, Exception):
                raise Exception('failed because parent task failed') from arg

        # Catch any exception from the task and return it as an 'result'.
        try:
            return Task.__call__(self, *args, **kwargs)
        except celery.exceptions.Retry:
            # Do not return a retry exception as it is raised when a task is retried.
            # If the task keeps failing eventually a MaxRetriesExceededError will come.
            raise
        except Exception as e:
            return e
