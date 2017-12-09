import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Adds some documentation artifacts to this project.'

    def handle(self, *args, **options):
        raise NotImplemented
        # failmap-admin graph_models organizations scanners map -o myapp_models.png

        # it's posisble to also include auth and other installed things by not specifying an app.
