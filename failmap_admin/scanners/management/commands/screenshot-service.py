import logging
from time import sleep

from django.core.management.base import BaseCommand

from failmap_admin.scanners.scanner_screenshot import screenshots_of_new_urls

logger = logging.getLogger(__package__)


class Command(BaseCommand):
    help = 'Create screenshots of urls that don\'t have a screenshot yet'

    def handle(self, *args, **options):
        try:
            while True:
                screenshots_of_new_urls()
                logger.info("No more endpoints to screenshot. Waiting 60 seconds for more.")
                sleep(60)
        except KeyboardInterrupt:
            logger.debug("Stopped. If this was killed when making screenshots: "
                         "please check if there are still some browsers running.")
