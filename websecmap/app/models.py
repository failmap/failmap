import importlib
import logging

from django.contrib.auth.models import User
from django.db import models

from taggit.managers import TaggableManager

from websecmap.app.fields import CompressedJSONField
from websecmap.celery import app

log = logging.getLogger(__name__)


class CompressedJSONFieldTest(models.Model):
    data = CompressedJSONField(help_text="Data in this fiels is json but compressed with gzip...")
    old_data = CompressedJSONField(
        help_text="Some data that might or might not be upgraded!", default={"hello": "world"}
    )


@app.task(queue="kickoff")
def create_function_job(function: str, **kwargs) -> None:
    """Helper to allow Jobs to be created using Celery Beat.

    function: complete path to a function inside a module. This will be executed.

    This function helps when not all tasks have been discovered or are called directly. It sets no requirement to how
    a module should look. Anything that composes tasks can be inserted here.
    """

    parts = function.split(".")
    module = ".".join(parts[0:-1])
    function_name = parts[-1]

    module = importlib.import_module(module)
    call = getattr(module, function_name, None)
    if not call:
        raise ValueError(f"Function {function_name} not found in {module}.")

    task = call(**kwargs)
    task.apply_async()


@app.task(queue="kickoff")
def create_job(task_module: str, **kwargs) -> None:
    return abstract_create_job(task_module, "compose_task", **kwargs)


@app.task(queue="kickoff")
def create_discover_job(task_module: str, **kwargs) -> None:
    return abstract_create_job(task_module, "compose_discover_task", **kwargs)


@app.task(queue="kickoff")
def create_verify_job(task_module: str, **kwargs) -> None:
    return abstract_create_job(task_module, "compose_verify_task", **kwargs)


@app.task(queue="kickoff")
def create_scan_job(task_module: str, **kwargs) -> None:
    return abstract_create_job(task_module, "compose_scan_task", **kwargs)


@app.task(queue="kickoff")
def create_planned_scan_job(task_module: str, **kwargs) -> None:
    return abstract_create_job(task_module, "compose_planned_scan_task", **kwargs)


@app.task(queue="kickoff")
def create_planned_discover_job(task_module: str, **kwargs) -> None:
    return abstract_create_job(task_module, "compose_planned_discover_task", **kwargs)


@app.task(queue="kickoff")
def create_planned_verify_job(task_module: str, **kwargs) -> None:
    return abstract_create_job(task_module, "compose_planned_verify_task", **kwargs)


@app.task(queue="kickoff")
def create_manual_scan_job(task_module: str, **kwargs) -> None:
    return abstract_create_job(task_module, "compose_manual_scan_task", **kwargs)


@app.task(queue="kickoff")
def create_manual_discover_job(task_module: str, **kwargs) -> None:
    return abstract_create_job(task_module, "compose_manual_discover_task", **kwargs)


@app.task(queue="kickoff")
def create_manual_verify_job(task_module: str, **kwargs) -> None:
    return abstract_create_job(task_module, "compose_manual_verify_task", **kwargs)


def abstract_create_job(task_module: str, method: str, **kwargs) -> None:
    # While the Job model was deleted, these methods are kept as all periodic tasks in various production machines
    # depend on them. Changing this means a lot of work to change administrative stuff, which is high risk no reward
    module = importlib.import_module(task_module)
    # call method from module:
    call_me = getattr(module, method)
    task = call_me(**kwargs)
    task.apply_async()


class Volunteer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    organization = models.TextField(max_length=200, blank=True, null=True)
    added_by = models.TextField(max_length=200, blank=True, null=True)
    notes = models.TextField(max_length=2048, blank=True, null=True)


class GameUser(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    # store the password in plain_text, so it's recoverable.
    password = models.TextField(max_length=200, blank=True, null=True)


class Translation(models.Model):
    key = models.CharField(max_length=200, blank=True, null=True)
    language_code = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="ISO 639-1 language code, see https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes",
    )
    value = models.TextField(blank=True, null=True)
    metadata_section = TaggableManager(blank=True)
    metadata_notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.key} - {self.language_code}"
