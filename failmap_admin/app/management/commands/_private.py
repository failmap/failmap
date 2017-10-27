"""Management command base classes."""

import logging

from django.conf import settings
from django.core.management.base import BaseCommand

log = logging.getLogger(__name__)


class TaskCommand(BaseCommand):
    """A command that performs it's intended behaviour through a Celery task.

    The task can be run directly, sync- and asynchronously.

    Direct execution will run the task as if it was a direct function call.

    Sync execution will use the Celery framework to execute the task on
    a (remote) worker destined to execute tasks of this type. It will wait for
    execution to complete and return the task result/logging.

    Async is like Synchronous execution but it will not wait for it to complete.
    No result or logging will be returned.

    Direct and sync methods allow the task to be interupted during execution
    using ctrl-c.

    Sync and async methods require connection to a message broker, direct does not.
    """

    task = None
    # it is a anti-pattern to instantiate empty lists/dicts as class parameters
    # but since management commands are contained in their own invocation this can fly
    args = list()
    kwargs = dict()

    def add_arguments(self, parser):
        """Add common argument for Celery tasks."""
        parser.add_argument(
            '-m',
            '--method',
            choices=[
                'direct',
                'sync',
                'async'],
            default='direct',
            help='Execute the task directly or via Celery queues.')

    def handle(self, *args, **options):
        """Command handle logic, eg: logging."""
        # set django loglevel based on `-v` argument
        verbosity = int(options['verbosity'])
        root_logger = logging.getLogger('')
        if verbosity == 2:
            root_logger.setLevel(logging.DEBUG)
        elif verbosity == 1:
            root_logger.setLevel(logging.INFO)
        elif verbosity == 0:
            root_logger.setLevel(logging.ERROR)

        # execute task based on selected method
        if options['method'] in ['sync', 'async']:
            task_id = self.task.apply_async(args=self.args, kwargs=self.kwargs)
            log.info('Task %s scheduled for execution.', task_id)
            if options['method'] == 'sync':
                return task_id.get()
        else:

            # by default execute the task directly without involving celery or a broker
            return self.task(*self.args, **self.kwargs)
