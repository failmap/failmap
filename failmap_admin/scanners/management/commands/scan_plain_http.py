import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Organization, Url
from failmap_admin.scanners.scanner_plain_http import ScannerPlainHttp

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Scan for http sites that don\'t have https'

    def handle(self, *args, **options):

        s = ScannerPlainHttp()
        s.scan()
