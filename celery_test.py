# https://realpython.com/blog/python/asynchronous-tasks-with-django-and-celery/
# https://github.com/failmap/admin/pull/2/files
# http://oddbird.net/2017/03/20/serializing-things/
# http://docs.celeryproject.org/en/latest/userguide/security.html

# Kept for reference, when (if) moving to celery.
# from __future__ import absolute_import
import os
from celery import Celery  # don't name your module celery, as Celery can not be found :)
from django.conf import settings

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'failmap_admin.settings')
app = Celery('celery_test', broker='pyamqp://myuser:mypassword@localhost/myvhost')

class Config:
    enable_utc = True
    timezone = 'Europe/London'
    accept_content = ['pickle']
    task_serializer = 'pickle'
    result_serializer = 'pickle'
    CELERY_ACCEPT_CONTENT = ['pickle']

app.config_from_object(Config)  # does not work. Somehow does nothing, in all examples given.
app.conf.accept_content = ['pickle']
app.conf.task_serializer = 'pickle'
app.conf.result_serializer = 'pickle'
app.conf.event_serializer = 'pickle'
print(app.conf)

app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# Any data transfered with pickle needs to be over https... you can inject arbitrary objects with
# this stuff... message signing makes it a bit better, not perfect as it peels the onion.
# see: https://blog.nelhage.com/2011/03/exploiting-pickle/
# Yet pickle is the only convenient way of transporting objects without having to lean in all kinds
# of directions to get the job done. Intermediate tables to store results could be an option.

@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))

@app.task
def add(x, y):
    return x + y