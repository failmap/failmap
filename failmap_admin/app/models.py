# coding=UTF-8
# from __future__ import unicode_literals

import datetime

import celery
from django.contrib.auth.models import User
from django.db import models
from jsonfield import JSONField

from ..app.common import ResultEncoder
from ..celery import app


class Job(models.Model):
    """An object to provide tracking of tasks."""

    name = models.CharField(max_length=255, help_text="name of the job")
    task = models.TextField(help_text="celery task signature in string form")
    result_id = models.CharField(unique=True, null=True, blank=True, max_length=255,
                                 help_text="celery asyncresult ID for tracing task")
    status = models.CharField(max_length=255, help_text="status of the job")
    result = JSONField(help_text="output of the task as JSON", encoder_class=ResultEncoder)

    created_on = models.DateTimeField(auto_now_add=True, blank=True, null=True, help_text="when task was created")
    finished_on = models.DateTimeField(blank=True, null=True, help_text="when task ended")
    created_by = models.ForeignKey(User, blank=True, null=True)

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

        # retrieve job object again (might have changed if celery was really fast or eager was enabled)
        job = Job.objects.get(id=job.id)
        job.result_id = result_id.id
        job.save()

        return job

    @staticmethod
    @app.task
    def store_result(result, job_id=None):
        """Celery task to store result of task after it has completed."""
        print(result, job_id)
        job = Job.objects.get(id=job_id)
        if not result:
            result = '-- task generated no result object --'
        job.result = result
        job.status = 'completed'
        job.finished_on = datetime.datetime.now()
        job.save()

    def __str__(self):
        return self.result_id
