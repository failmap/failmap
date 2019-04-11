import importlib
import json

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django_celery_beat.models import PeriodicTask

from websecmap.app.models import Job
from websecmap.celery import app


@pytest.fixture
def celery(settings):
    """Common setup for running (simulated) celery tasks inside tests."""
    # don't let celery contact broker, execute tasks directly
    settings.CELERY_TASK_ALWAYS_EAGER = True


@app.task(queue='default')
def dummy(result=True):
    """Dummy celery task for testing."""
    if result:
        return 'result'


def test_job(db, mocker, celery):
    """Test creating task wrapped in a job."""

    request = mocker.Mock()
    user = User(username='testuser')
    user.save()
    request.user = user

    job = Job.create(dummy.s(), 'a-name', request)

    assert job.result_id
    assert job.status == 'created'

    # result after task has been processed by celery
    job.refresh_from_db()
    assert job.status == 'completed'
    assert job.result == 'result'
    assert job.task == 'websecmap.app.tests.dummy()'
    assert job.created_by == user
    assert str(job) == 'a-name'


def test_job_no_result(db, celery):
    """Task returning no result should not break stuff."""

    job = Job.create(dummy.s(False), 'a-name', None)

    assert job.result_id
    assert job.status == 'created'

    # result after task has been processed by celery
    job.refresh_from_db()
    assert job.status == 'completed'
    assert job.result == '-- task generated no result object --'
    assert job.task == 'websecmap.app.tests.dummy(False)'


def test_periodic_tasks(db):
    """
    Loads all periodic tasks from the production json and runs each and every one of them. The results of those
    tasks are discarded. The goal is to confirm that there are no incorrectly configured periodic tasks.
    """

    verify_periodic_tasks_from_fixture('production.json')
    verify_periodic_tasks_from_fixture('development.json')


def verify_periodic_tasks_from_fixture(fixture):

    call_command("loaddata", fixture, verbosity=0)

    periodic_tasks = PeriodicTask.objects.all()
    for periodic_task in periodic_tasks:

        # only test websecmap modules.
        if not periodic_task.task.startswith('websecmap'):
            continue

        module_name = periodic_task.task[0:periodic_task.task.rfind('.')]
        method = periodic_task.task.split('.')[-1]

        loaded = True
        has_method = False
        try:
            module = importlib.import_module(module_name)
            has_method = hasattr(module, method)
        except ModuleNotFoundError:
            loaded = False

        # include the module and method for easier debugging if this test fails.
        assert module_name == module_name and method == method and has_method is True and loaded is True

        if periodic_task.task in ['websecmap.app.models.create_job', 'websecmap.app.models.create_discover_job',
                                  'websecmap.app.models.create_verify_job', 'websecmap.app.models.create_scan_job']:

            # also validate that the argument exists.
            args = json.loads(periodic_task.args)
            # will crash if the module does not exist.
            loaded = True
            try:
                module = importlib.import_module(args[0])
            except ModuleNotFoundError:
                loaded = False

            # add the scanner name for easier debugging output.
            assert args[0] == args[0] and loaded is True

            # specific types of tasks require specific methods to be present.

            if args[0] == 'websecmap.app.models.create_job':
                has_method = hasattr(module, 'compose_task')
                assert args[0] == args[0] and 'compose_task' == 'compose_task' and has_method is True

            if args[0] == 'websecmap.app.models.create_verify_job':
                has_method = hasattr(module, 'compose_verify_task')
                assert args[0] == args[0] and 'compose_verify_task' == 'compose_verify_task' and has_method is True

            if args[0] == 'websecmap.app.models.create_discover_job':
                has_method = hasattr(module, 'compose_discover_task')
                assert args[0] == args[0] and 'compose_discover_task' == 'compose_discover_task' and has_method is True

            if args[0] == 'websecmap.app.models.create_scan_job':
                has_method = hasattr(module, 'compose_scan_task')
                assert args[0] == args[0] and 'compose_scan_task' == 'compose_scan_task' and has_method is True
