import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.impact import report_impact_to_commandline

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Shows the impact of this installation."""

    def handle(self, *args, **options):
        report_impact_to_commandline()
