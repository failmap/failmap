# coding=UTF-8
# from __future__ import unicode_literals

import importlib
import logging
import re

import celery
from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from jsonfield import JSONField

from websecmap.celery import app

log = logging.getLogger(__name__)


def censor_sensitive_data(data):
    # Heuristicly remove sensitive data from the task output. This will not cover all cases.
    # This will prevent password leakage from database leaks.

    # Full Match: pass='.....'
    # Group 1: pass=
    # Group 2: pass
    # Group 3: " (' or ", enclosing)
    # Replaces it to fieldname + quote + asteriks + quote
    # https://regex101.com/
    # @regex101: (note that \3 has to be written as \g3, thus ((pass|password|key|secret|hash|salt)=)(['"]).*?\g3
    # The signifier for a secret can be anywhere in the variable name.
    # https://stackoverflow.com/questions/10120295/valid-characters-in-a-python-class-name
    data = re.sub(
        r"(?i)([a-zA-Z0-9_]*?(sessionid|token|pass|password|key|secret|hash|salt)[a-zA-Z0-9_]*?=)(['\"]).*?\3",
        r"\1\3********************\3", data, flags=re.MULTILINE)
    return data


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
        data = self.cleaned_data['task'][:1000*1]

        return censor_sensitive_data(data)

    @classmethod
    def create(cls, task: celery.Task, name: str, request, *args, **kwargs) -> 'Job':
        """Create job object and publish task on celery queue."""
        # create database object
        job = cls(task=censor_sensitive_data(str(task)))
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
        try:
            job.save(update_fields=['result', 'status', 'finished_on'])
        except TypeError:
            job.result = "Job returned a '%s' which could not be serialized. Job finished." % type(result)
            job.save(update_fields=['result', 'status', 'finished_on'])

    def __str__(self):
        return self.name


@app.task(queue='storage')
def create_function_job(function: str, **kwargs):
    """Helper to allow Jobs to be created using Celery Beat.

    function: complete path to a function inside a module. This will be executed.

    This function helps when not all tasks have been discovered or are called directly. It sets no requirement to how
    a module should look. Anything that composes tasks can be inserted here.
    """

    parts = function.split('.')
    module = ".".join(parts[0:-1])
    function_name = parts[-1]

    module = importlib.import_module(module)
    call = getattr(module, function_name, None)
    if not call:
        raise ValueError('Function %s not found in %s.' % (function_name, module))

    task = call(**kwargs)

    return Job.create(task, function, None)


@app.task(queue='storage')
def create_planned_scan_job(task_module: str, **kwargs):
    """Helper to allow Jobs to be created using Celery Beat.

    task_module: module from which to call `compose_discover_task` which results in the task to be executed
    """

    module = importlib.import_module(task_module)
    task = module.compose_planned_scan_task(**kwargs)

    return Job.create(task, task_module, None)


@app.task(queue='storage')
def create_planned_discover_job(task_module: str, **kwargs):
    """Helper to allow Jobs to be created using Celery Beat.

    task_module: module from which to call `compose_discover_task` which results in the task to be executed
    """

    module = importlib.import_module(task_module)
    task = module.compose_planned_discover_task(**kwargs)

    return Job.create(task, task_module, None)


@app.task(queue='storage')
def create_planned_verify_job(task_module: str, **kwargs):
    """Helper to allow Jobs to be created using Celery Beat.

    task_module: module from which to call `compose_discover_task` which results in the task to be executed
    """

    module = importlib.import_module(task_module)
    task = module.compose_planned_verify_task(**kwargs)

    return Job.create(task, task_module, None)


@app.task(queue='storage')
def create_manual_scan_job(task_module: str, **kwargs):
    """Helper to allow Jobs to be created using Celery Beat.

    task_module: module from which to call `compose_discover_task` which results in the task to be executed
    """

    module = importlib.import_module(task_module)
    task = module.compose_manual_scan_task(**kwargs)

    return Job.create(task, task_module, None)


@app.task(queue='storage')
def create_manual_discover_job(task_module: str, **kwargs):
    """Helper to allow Jobs to be created using Celery Beat.

    task_module: module from which to call `compose_discover_task` which results in the task to be executed
    """

    module = importlib.import_module(task_module)
    task = module.compose_manual_discover_task(**kwargs)

    return Job.create(task, task_module, None)


@app.task(queue='storage')
def create_manual_verify_job(task_module: str, **kwargs):
    """Helper to allow Jobs to be created using Celery Beat.

    task_module: module from which to call `compose_discover_task` which results in the task to be executed
    """

    module = importlib.import_module(task_module)
    task = module.compose_manual_verify_task(**kwargs)

    return Job.create(task, task_module, None)


class Volunteer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    organization = models.TextField(max_length=200, blank=True, null=True)
    added_by = models.TextField(max_length=200, blank=True, null=True)
    notes = models.TextField(max_length=2048, blank=True, null=True)


class GameUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    # store the password in plain_text, so it's recoverable.
    password = models.TextField(max_length=200, blank=True, null=True)
