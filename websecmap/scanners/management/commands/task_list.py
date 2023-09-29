from websecmap.celery import app
from django.core.management.base import BaseCommand


# don't know if the taskcommand stuff clashes
class Command(BaseCommand):
    def handle(self, *args, **options):
        for task in app.tasks.keys():
            print(task)
