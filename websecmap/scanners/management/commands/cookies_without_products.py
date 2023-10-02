import logging

from django.core.management.base import BaseCommand


log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Show cookie names for which no product has been determined by Cookie Indicators."""

    def handle(self, *args, **options):
        pass
