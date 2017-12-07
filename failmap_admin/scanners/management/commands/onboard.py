import logging

from django.core.management.base import BaseCommand

from failmap_admin.scanners.onboard import onboard_new_urls

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Automatically performs initial scans and tests on new urls.'

    def handle(self, *args, **options):
        onboard_new_urls()
