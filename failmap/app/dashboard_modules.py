# http://jet.readthedocs.io/en/latest/dashboard_custom_module.html
# needs: http://jet.readthedocs.io/en/latest/dashboard_custom_module.html#inherit-dashboard-module
# https://github.com/john-kurkowski/tldextract
# https://www.dabapps.com/blog/higher-level-query-api-django-orm/
# https://docs.djangoproject.com/en/1.10/intro/overview/#enjoy-the-free-api
# https://docs.djangoproject.com/en/1.10/topics/db/queries/

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse
from jet.dashboard.modules import DashboardModule

from failmap.map.rating import rebuild_ratings as rebuild_ratings_task

from ..celery import PRIO_HIGH
from .models import Job


class RebuildRatings(DashboardModule):
    title = 'Rebuild Ratings'
    title_url = 'Rebuild Ratings'

    template = 'app/templates/admin/RebuildRatings.html'


@login_required
def rebuild_ratings(request):
    """Create rebuild ratings task and dispatch using a Job to allow the user to track progress."""
    name = 'Rebuild ratings'
    # create a Task signature for rebuilding ratings, wrap this inside a Job
    # to have it trackable by the user in the admin interface
    task = rebuild_ratings_task.s()
    job = Job.create(task, name, request, priority=PRIO_HIGH)

    # tell the user where to find the Job that was just created
    link = reverse('admin:app_job_change', args=(job.id,))
    messages.success(request, '%s: job created, id: <a href="%s">%s</a>' % (name, link, str(job)))

    return redirect(reverse('admin:index'))
