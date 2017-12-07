import logging

from django.core.management.base import BaseCommand

from failmap_admin.scanners.scanner_screenshot import screenshots_of_new_urls

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Create screenshots of urls that don\'t have a screenshot yet'

    def handle(self, *args, **options):
        logger.info("Creating screenshots of new urls.")
        screenshots_of_new_urls()
