# https://realpython.com/blog/python/asynchronous-tasks-with-django-and-celery/
# https://github.com/failmap/admin/pull/2/files
# http://oddbird.net/2017/03/20/serializing-things/
# http://docs.celeryproject.org/en/latest/userguide/security.html

# Kept for reference, when (if) moving to celery.
# from __future__ import absolute_import
import os

from celery import Celery  # don't name your module celery, as Celery can not be found :)
from django.conf import settings

app = Celery(__name__)
app.config_from_object('django.conf:settings')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))


@app.task
def add(x, y):
    return x + y
