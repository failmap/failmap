import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.scanner.security_policies import initialize_security_policies

log = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        initialize_security_policies()
