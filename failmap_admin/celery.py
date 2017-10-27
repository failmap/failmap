# https://realpython.com/blog/python/asynchronous-tasks-with-django-and-celery/
# https://github.com/failmap/admin/pull/2/files
# http://oddbird.net/2017/03/20/serializing-things/
# http://docs.celeryproject.org/en/latest/userguide/security.html

# Kept for reference, when (if) moving to celery.
# from __future__ import absolute_import
import os

from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "failmap_admin.settings")

app = Celery(__name__)
app.config_from_object('django.conf:settings')
# autodiscover all celery tasks in tasks.py files inside failmap_admin modules
appname = __name__.split('.', 1)[0]
app.autodiscover_tasks([app for app in settings.INSTALLED_APPS if app.startswith(appname)])


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))
