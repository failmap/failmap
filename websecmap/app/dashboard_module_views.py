from django.http import JsonResponse
from django.urls import re_path
from jet.dashboard import dashboard

from websecmap.celery import status


def task_processing_status(request):
    """Return a JSON object with current status of task processing."""

    return JsonResponse(status())


dashboard.urls.register_urls(
    [
        re_path(r"^task_processing_status/", task_processing_status, name="task-processing-status"),
    ]
)
