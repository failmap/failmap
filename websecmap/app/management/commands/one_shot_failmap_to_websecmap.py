# Some help to translate the django part.
# This tries to help you avoid remembering the "messages" mess from Django.
import logging

from django.core.management.base import BaseCommand
from django_celery_beat.models import PeriodicTask

log = logging.getLogger(__package__)


class Command(BaseCommand):
    help = """ Converts failmap to websecmap in all tasks."""

    def handle(self, *args, **options):
        periodic_tasks = PeriodicTask.objects.all().filter()

        for task in periodic_tasks:
            log.debug(task)
            log.debug(dir(task))

            task.name = task.name.replace('failmap', 'websecmap')
            task.task = task.task.replace('failmap', 'websecmap')
            task.save()
