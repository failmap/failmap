# https://realpython.com/blog/python/asynchronous-tasks-with-django-and-celery/
# https://github.com/failmap/admin/pull/2/files
# http://oddbird.net/2017/03/20/serializing-things/
# http://docs.celeryproject.org/en/latest/userguide/security.html

from __future__ import absolute_import
import os
from celery import Celery
from django.conf import settings

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'failmap_admin.settings')
app = Celery('failmap', broker_url='memory://')

# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

# Any data transfered with pickle needs to be over https... you can inject arbitrary objects with
# this stuff... message signing makes it a bit better, not perfect as it peels the onion.
# see: https://blog.nelhage.com/2011/03/exploiting-pickle/

# you cannot use class methods... so basically stop thinking OO. That's a big step.

@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))
