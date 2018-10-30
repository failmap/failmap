# coding=UTF-8
# from __future__ import unicode_literals

import importlib

import celery
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from jsonfield import JSONField

from ..celery import app


class Job(models.Model):
    """Wrap any Celery task to easily 'manage' it from Django."""

    name = models.CharField(max_length=255, help_text="name of the job")
    task = models.TextField(help_text="celery task signature in string form")
    result_id = models.CharField(unique=True, null=True, blank=True, max_length=255,
                                 help_text="celery asyncresult ID for tracing task")
    status = models.CharField(max_length=255, help_text="status of the job")
    result = JSONField(help_text="output of the task as JSON")  # JSONfield (not django-jsonfield) does not
    # encoder_class=ResultEncoder

    created_on = models.DateTimeField(auto_now_add=True, blank=True, null=True, help_text="when task was created")
    finished_on = models.DateTimeField(blank=True, null=True, help_text="when task ended")

    # TypeError: __init__() missing 1 required positional argument: 'on_delete'
    # probably because of blank and/or default.
    created_by = models.ForeignKey(User, blank=True, null=True, on_delete=models.CASCADE,)

    def clean_task(self):
        """Truncate long task signatures as they result in mysql issues.

        https://gitlab.com/failmap/server/issues/24

        Task signatures are for informational purpose and not functionally required. Currently
        there is no reason to keep large signatures so truncating to arbitrary limit of 1k.
        """
        return self.cleaned_data['task'][:1000*1]

    @classmethod
    def create(cls, task: celery.Task, name: str, request, *args, **kwargs) -> 'Job':
        """Create job object and publish task on celery queue."""
        # create database object
        job = cls(task=str(task))
        if request:
            job.created_by = request.user
        job.name = name[:255]
        job.status = 'created'
        job.save()

        # publish original task which stores the result in this Job object
        result_id = (task | cls.store_result.s(job_id=job.id)).apply_async(*args, **kwargs)

        # store the task async result ID for reference
        job.result_id = result_id.id
        job.save(update_fields=['result_id'])

        return job

    @staticmethod
    @app.task(queue='storage')
    def store_result(result, job_id=None):
        """Celery task to store result of wrapped task after it has completed."""
        job = Job.objects.get(id=job_id)
        if not result:
            result = '-- task generated no result object --'
        job.result = result
        job.status = 'completed'
        job.finished_on = timezone.now()
        job.save(update_fields=['result', 'status', 'finished_on'])

    def __str__(self):
        return self.name


@app.task(queue='storage')
def create_job(task_module: str):
    """Helper to allow Jobs to be created using Celery Beat.

    task_module: module from which to call `compose_discover_task` which results in the task to be executed
    """

    module = importlib.import_module(task_module)
    task = module.compose_task()

    return Job.create(task, task_module, None)


@app.task(queue='storage')
def create_discover_job(task_module: str):
    """Helper to allow Jobs to be created using Celery Beat.

    task_module: module from which to call `compose_discover_task` which results in the task to be executed
    """

    module = importlib.import_module(task_module)
    task = module.compose_discover_task()

    return Job.create(task, task_module, None)


@app.task(queue='storage')
def create_verify_job(task_module: str):
    """Helper to allow Jobs to be created using Celery Beat.

    task_module: module from which to call `compose_discover_task` which results in the task to be executed
    """

    module = importlib.import_module(task_module)
    task = module.compose_verify_task()

    return Job.create(task, task_module, None)


class Volunteer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    organization = models.TextField(max_length=200, blank=True, null=True)
    added_by = models.TextField(max_length=200, blank=True, null=True)
    notes = models.TextField(max_length=2048, blank=True, null=True)
