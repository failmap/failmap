import logging

from django.core.management.base import BaseCommand

from websecmap.scanners.cleaners import clean_plain_http_no_https_redirect_no_https_on_standard_port_evidence

log = logging.getLogger(__name__)


class Command(BaseCommand):
    def handle(self, *args, **options):
        clean_plain_http_no_https_redirect_no_https_on_standard_port_evidence()
