import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.scanner import internet_nl_mail

log = logging.getLogger(__name__)


class Command(BaseCommand):
    """Checks running internet nl scans."""

    help = __doc__

    def handle(self, *args, **options):
        internet_nl_mail.check_running_scans()
