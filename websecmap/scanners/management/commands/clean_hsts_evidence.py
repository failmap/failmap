import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.cleaners import clean_http_security_header_strict_transport_security

log = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        clean_http_security_header_strict_transport_security()
