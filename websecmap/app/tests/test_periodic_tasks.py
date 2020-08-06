import importlib
import json
import logging

from django.core.management import call_command
from django_celery_beat.models import PeriodicTask

log = logging.getLogger(__name__)


def test_periodic_tasks(db):
    """
    Loads all periodic tasks from the production json and runs each and every one of them. The results of those
    tasks are discarded. The goal is to confirm that there are no incorrectly configured periodic tasks.
    """

    verify_periodic_tasks_from_fixture('periodic_tasks.json')
    verify_periodic_tasks_from_fixture('development_periodic_tasks.json')


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
            log.debug(f"Checking of the imported module {module_name} actually has the method {method}.")
            module = importlib.import_module(module_name)
            has_method = hasattr(module, method)
        except ModuleNotFoundError:
            log.error(f"Imported module {module_name} does not have the method {method}.")
            loaded = False

        # include the module and method for easier debugging if this test fails.
        assert has_method is True
        assert loaded is True

        if periodic_task.task in ['websecmap.app.models.create_planned_discover_job',
                                  'websecmap.app.models.create_planned_verify_job',
                                  'websecmap.app.models.create_planned_scan_job',
                                  ]:

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
            if args[0] == 'websecmap.app.models.create_planned_verify_job':
                has_method = hasattr(module, 'create_planned_verify_task')
                assert args[0] == args[0] and has_method is True

            if args[0] == 'websecmap.app.models.create_planned_discover_job':
                has_method = hasattr(module, 'compose_planned_discover_task')
                assert args[0] == args[0] and has_method is True

            if args[0] == 'websecmap.app.models.create_planned_scan_job':
                has_method = hasattr(module, 'compose_planned_scan_task')
                assert args[0] == args[0] and has_method is True
