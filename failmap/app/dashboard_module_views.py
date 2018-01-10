from django.conf.urls import url
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from jet.dashboard import dashboard

from failmap.map.rating import rebuild_ratings as rebuild_ratings_task

from ..celery import PRIO_HIGH, app
from .models import Job


def task_processing_status(request):
    """Return a JSON object with current status of task processing."""

    inspect = app.control.inspect()

    # query workforce statistics using control.inspect API and extract some relevant data from it
    stats = inspect.stats() or {}
    active = inspect.active()
    workers = [{
        'name': worker_name,
        'tasks_processed': sum(worker_stats['total'].values()),
        'tasks_active': len(active[worker_name]),
    } for worker_name, worker_stats in stats.items()]

    status = {'workers': workers}

    return JsonResponse(status)


dashboard.urls.register_urls([
    url(
        r'^task_processing_status/',
        task_processing_status,
        name='task-processing-status'
    ),
])


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


dashboard.urls.register_urls([
    url(
        r'^rebuild_ratings/',
        rebuild_ratings,
        name='rebuild-ratings'
    ),
])
