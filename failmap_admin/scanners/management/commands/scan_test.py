import logging

from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand

from failmap_admin.organizations.models import Organization
from failmap_admin.scanners.management.commands.scan_tls_qualys import Command as XCommand
from failmap_admin.scanners.managers import StateManager
from failmap_admin.scanners.scanner_dns import ScannerDns

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Development command'

    def handle(self, *args, **options):
        XCommand.scannable_new_urls()
